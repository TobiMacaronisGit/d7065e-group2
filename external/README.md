# external/ — course-provided infrastructure (vendored, unmodified)

`buildingsim/` and `occupancysim/` are an **unmodified copy** of the course repository
<https://github.com/eislab-cps/D7065E>, so that this repository builds and runs on its own
(`docker compose up --build`) without a second checkout.

| | |
|---|---|
| Source | `github.com/eislab-cps/D7065E`, folders `buildingsim/` and `occupancysim/` |
| Commit | `80a4c5928e675feabe81dd14b490c2123aea2a1b` (2026-09-02) |
| Copied with | `git -C <course-repo> archive HEAD buildingsim occupancysim \| tar -x -C external` |
| License | BuildSim: MIT, © 2026 Johan Kristiansson (`buildingsim/LICENSE`). occupancysim: course material, no license file in the source. |

Not our code — do not edit. To update, re-run the copy command against a newer course-repo commit
and update the commit hash above.
