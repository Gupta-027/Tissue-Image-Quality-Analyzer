# Documentation

Start with the project guide, then use the interview guide to practice explaining
the implementation. Read the references when you need a formula or a command.

| Document | What it helps you do |
|---|---|
| [Project guide](guides/project_guide.md) | Understand the folders, follow one tile through the code, and choose a reading order |
| [Interview guide](guides/interview_guide.md) | Give a short pitch, demonstrate the app, and answer technical questions |
| [Setup and commands](reference/setup.md) | Install, download slides, run the app, analyze from the CLI, and reproduce experiments |
| [Methods](reference/methods.md) | Explain segmentation, coordinate mapping, focus formulas, and evaluation |
| [Sample data](reference/data_sources.md) | Check sample provenance, licensing, sizes, and pyramid metadata |
| [Interface notes](reference/ui_design.md) | Understand the overlay legend, layout, and accessibility choices |
| [Validation log](reports/validation.md) | See the commands actually run and their outcomes |
| [Browser validation](reports/browser_validation.md) | See the real-slide interaction checks and the selection bug that was fixed |
| [Recorded benchmark report](reports/benchmark_results.json) | Inspect the saved measurements and split metadata |

`guides/` teaches the project, `reference/` holds implementation details, and
`reports/` preserves evidence. Downloaded slides and generated results live in
the repository's ignored `data/` and `outputs/` folders.
