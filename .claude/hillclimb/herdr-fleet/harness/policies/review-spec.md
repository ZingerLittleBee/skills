Team review policy for this repository (applies to every code review you do):

- docs/SPEC.md is normative. A change that touches amount parsing must accept
  every amount spelling listed under "Amount syntax" and reject everything
  else with ValueError; a candidate that leaves any listed spelling
  unsupported fails an acceptance criterion and is a P1 finding, even if the
  task text only mentioned some of the spellings.
