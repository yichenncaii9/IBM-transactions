# IS459 submission check

The course brief in `knowledge/IS459 Project_G2.pdf` asks for a final presentation, source code, and narrated videos showing both pipeline setup and a full run. The appendix of the presentation must link to the YouTube videos. The presentation also needs an ingestion-to-visualization architecture diagram and an individual-contributions slide.

## Available evidence

- This repository contains the Q1 and Q2 analysis code, Glue cleaning and pattern-parsing scripts recovered from the deployed jobs, Glue rule-feature jobs, graph analysis, model notebook, dashboard, tests, and prepared dashboard CSVs.
- The final presentation deck is kept outside this repository at `../IS459_G2T8_Final_Deck.pptx`. It has an architecture diagram on slide 8 and individual contributions on slide 18.
- A narrated run video and three shorter demo clips are kept outside this repository in `../video_CC 2/`. They are intentionally excluded from the code repository.
- The two evaluation CSVs removed from `q1d-eval/out/` during cleanup were byte-identical to the retained copies in `dashboard/data/`. The removed notes and backups are not required deliverables.

## Before submission

1. Record or locate a narrated **setup** video. The available run video does not, by itself, establish that setup is demonstrated end to end.
2. Upload the setup and run videos to YouTube, verify playback and permissions, and replace both `link to be added` entries on slide 19 of the final deck with working URLs.
3. Replace the three `Insert → Video` placeholders on slides 6, 9, and 11 with the available clips, or remove those placeholders and narrate the clips live.
4. Reconcile the slide 5/8 architecture and demo narration with the actual code and AWS configuration. The cleaning and pattern-parsing scripts are now in `glue/`, and the Q2 corridor SQL is in `q2/corridors.sql`. The repository still lacks deployment configuration and some upstream Athena table definitions (`accounts_raw`, `basel_scores`, `rule_hits_full`, and `rule_hits_neo4j_full`). Export those if source-level reproduction of the complete AWS pipeline is expected.
5. Upload the final deck and source code or links before class. After the final presentation, delete project AWS resources as the brief requires.

The local code cannot prove the current AWS deployment, video uploads, or slide links. Check those items against the live resources before describing the submission as complete.
