local home = assert(os.getenv("HOME"), "HOME is required for the Rex shortcuts.")
local documents = home .. "/Documents"
local worktree_root = documents .. "/worktree"

rex.action{
  name = "new_documents_session",
  title = "New Session in Documents",
  category = "Session",
  run = function(ctx)
    if ctx.server and ctx.server ~= "" then
      rex.client.queue("session.new")
      return
    end

    local session, err = rex.call("session.create", {
      initial_windows = {{
        layout = rex.layout.block{
          flavor = "com.superlogical.terminal.shell",
          options = { cwd = documents },
        },
      }},
    })
    if not session then
      error(err)
    end

    rex.client.queue("session.select", { session_id = session.session_id })
    return session
  end,
}

rex.unbind("cmd+n", "session.new")
rex.bind("cmd+n", "new_documents_session")

local function run_command(argv, timeout)
  local result, err = rex.exec(argv, { timeout = timeout or 10 })
  if not result then
    error(err, 2)
  end
  if not result.ok then
    local detail = result.stderr:gsub("%s+$", "")
    error(detail ~= "" and detail or ("Command failed: " .. argv[1]), 2)
  end
  return result.stdout
end

local function terminal_directory(block_id)
  if not block_id then
    return nil
  end
  local result = rex.block.call("com.superlogical.terminal", "pwd", { block_id = block_id })
  local path = result and result.pwd and result.pwd:match("^file://[^/]*(/.*)$")
  if path then
    return (path:gsub("%%(%x%x)", function(hex)
      return string.char(tonumber(hex, 16))
    end))
  end

  local process = rex.block.call("com.superlogical.terminal", "process", { block_id = block_id })
  local foreground = process and process.foreground
  local cwd = foreground and foreground.cwd
  if cwd and cwd:sub(1, 1) == "/" and foreground.name ~= "ssh" and foreground.name ~= "mosh-client" then
    return cwd
  end
end

local function active_terminal_directory()
  local session = rex.session.view()
  if not session or not session.windows then
    return nil
  end
  for _, window in ipairs(session.windows) do
    if window.window_id == session.active_window_id then
      return terminal_directory(window.focused_block_id)
    end
  end
end

local function git_directory(directory)
  if directory then
    local result = rex.exec({ "git", "-C", directory, "rev-parse", "--is-inside-work-tree" })
    if result and result.ok and result.stdout == "true\n" then
      return directory
    end
  end
end

local function suggested_worktree_branch(repo, repo_worktrees)
  local adjectives = { "brave", "calm", "clear", "green", "lucky", "quiet", "rapid", "silver" }
  local nouns = { "river", "cloud", "field", "forest", "harbor", "meadow", "stone", "valley" }
  local refs = "\n" .. run_command({
    "git", "-C", repo, "for-each-ref", "--format=%(refname)", "refs/heads",
  })

  for _ = 1, 20 do
    local seed = math.random(0, 0xffff)
    local adjective = adjectives[seed % #adjectives + 1]
    local noun = nouns[math.floor(seed / #adjectives) % #nouns + 1]
    local branch = string.format("%s-%s-%04x", adjective, noun, seed)
    local ref = "\nrefs/heads/" .. branch
    if not refs:find(ref .. "\n", 1, true) and not refs:find(ref .. "/", 1, true) then
      local path = repo_worktrees .. "/" .. branch
      local available, err = rex.exec({ "/bin/test", "!", "-e", path, "-a", "!", "-L", path })
      if not available then
        error(err)
      end
      if available.ok then
        return branch
      end
    end
  end

  error("Could not find an available worktree branch name.")
end

rex.action{
  name = "new_worktree_tab",
  title = "New Worktree Tab…",
  category = "Session",
  args = { repo = "string?", branch = "string?", base = "string?" },
  run = function(ctx, args)
    if ctx.server and ctx.server ~= "" then
      error("Open the local Rex workspace to create a local worktree.")
    end
    if not ctx.session_id then
      error("Open a Rex session before creating a worktree tab.")
    end

    local repo = args.repo or git_directory(terminal_directory(ctx.block_id))
    if not repo then
      local suggested = not ctx.block_id and git_directory(active_terminal_directory()) or nil
      repo = rex.ui.input{
        title = "Git repository directory",
        placeholder = "~/Documents/project",
        value = suggested,
        confirm = "Use repository",
      }
      if repo == nil then return end
    end
    repo = repo:gsub("^~/", home .. "/")
    if repo:sub(1, 1) ~= "/" then
      error("Enter an absolute repository directory or a path starting with ~/.")
    end

    local worktrees = run_command({ "git", "-C", repo, "worktree", "list", "--porcelain", "-z" })
    local main_directory = worktrees:match("^worktree ([^%z]+)")
    local repo_name = main_directory and main_directory:match("([^/]+)/*$")
    if not repo_name then
      error("Git did not report the main worktree.")
    end

    local repo_worktrees = worktree_root .. "/" .. repo_name
    local branch = args.branch or rex.ui.input{
      title = "New branch",
      value = suggested_worktree_branch(repo, repo_worktrees),
    }
    if branch == nil then return end
    if branch == "" or branch:sub(1, 1) == "-" then
      error("Enter a new Git branch name.")
    end
    run_command({ "git", "check-ref-format", "refs/heads/" .. branch })

    local base = args.base or rex.ui.input{
      title = "Start from branch or commit",
      value = "HEAD",
      confirm = "Create worktree",
    }
    if base == nil then return end
    local commit = run_command({
      "git", "-C", repo, "rev-parse", "--verify", "--end-of-options", base .. "^{commit}",
    }):gsub("%s+$", "")

    local directory = repo_worktrees .. "/" .. branch
    run_command({ "/bin/mkdir", "-p", repo_worktrees })
    run_command({ "git", "-C", repo, "worktree", "add", "-b", branch, "--", directory, commit }, 120)

    local tab, err = rex.call("session.new_window", {
      session_id = ctx.session_id,
      window_label = #branch <= 128 and branch or nil,
      focus = true,
      layout = rex.layout.block{
        flavor = "com.superlogical.terminal.shell",
        options = { cwd = directory },
      },
    })
    if not tab then
      error("Worktree created at " .. directory .. ". Could not open the Rex tab: " .. err)
    end
    local client = ctx.client_id and rex.call("client.inspect", { client_id = ctx.client_id })
    if client and client.client.info and client.client.info.kind == "app" then
      rex.client.queue("session.select", {
        session_id = ctx.session_id,
        window_id = tab.window_id,
      })
    end
    return tab
  end,
}

rex.bind("ctrl+alt+cmd+n", "new_worktree_tab")

rex.action{
  name = "remove_current_worktree",
  title = "Remove Current Git Worktree",
  category = "Session",
  run = function(ctx)
    if ctx.server and ctx.server ~= "" then
      error("Open the local Rex workspace to remove a local worktree.")
    end
    if not ctx.block_id then
      error("Focus a terminal pane in a linked Git worktree.")
    end

    local terminal = rex.block.call("com.superlogical.terminal", "process", {})
    local foreground = terminal and terminal.foreground
    local cwd = foreground and foreground.cwd
    if not cwd or cwd:sub(1, 1) ~= "/" then
      error("Could not determine the focused terminal's working directory.")
    end
    if foreground.name == "ssh" or foreground.name == "mosh-client" then
      error("Focus a local terminal pane in a linked Git worktree.")
    end

    local root = run_command({ "git", "-C", cwd, "rev-parse", "--show-toplevel" }):gsub("\n$", "")
    if cwd ~= root and cwd:sub(1, #root + 1) ~= root .. "/" then
      error("The focused terminal is not inside the detected Git worktree.")
    end

    local worktrees = run_command({ "git", "-C", root, "worktree", "list", "--porcelain", "-z" })
    local _, entry_start = worktrees:find("\0\0worktree " .. root .. "\0", 1, true)
    if not entry_start then
      error("Only linked Git worktrees can be removed. The main checkout is protected.")
    end

    local entry_end = worktrees:find("\0\0", entry_start, true) or #worktrees
    local entry = worktrees:sub(entry_start, entry_end)
    if entry:find("\0detached\0", 1, true) then
      local refs = run_command({
        "git", "-C", root, "for-each-ref", "--count=1", "--contains=HEAD", "--format=%(refname)",
        "refs/heads", "refs/remotes", "refs/tags",
      })
      if refs == "" then
        error("Save the detached HEAD on a branch before removing this worktree.")
      end
    end

    local changes = run_command({
      "git", "-C", root, "status", "--porcelain=v1", "-z", "--untracked-files=normal",
      "--ignored=matching", "--ignore-submodules=none",
    }, 60)
    if changes ~= "" then
      error("This worktree has modified, untracked, or ignored files. Review them before removing it.")
    end

    local placement, err = rex.session.describe_block{ block_id = ctx.block_id }
    if not placement then
      error(err)
    end
    local window_id = placement.block.window_id
    if not window_id then
      error("Focus a terminal in a Rex tab before removing its worktree.")
    end

    run_command({ "git", "-C", root, "worktree", "remove", "--", root }, 120)
    local closed, close_err = rex.session.close_window{ window_id = window_id }
    if not closed then
      error("Worktree removed at " .. root .. ". Could not close its Rex tab: " .. close_err)
    end
    return { removed_worktree = root, closed_window_id = window_id }
  end,
}

rex.bind("ctrl+alt+cmd+x", "remove_current_worktree")
