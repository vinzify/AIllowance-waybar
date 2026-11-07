# Contributing

Small fixes, clearer documentation, and provider compatibility improvements are welcome.

1. Open an issue describing the problem or proposed change.
2. Use an isolated branch and add synthetic fixtures for new report shapes.
3. Run the tests and ShellCheck commands in the README.
4. Submit a pull request explaining the behaviour change and validation.

Never commit real account reports, tokens, authentication files, personal screenshots, or CLI logs. Redact identifiers and balances before sharing diagnostics. Preserve the distinction between zero, missing, stale, and expired data. A failed refresh must not silently become a full allowance.

Keep the runtime lightweight, noninteractive, and free of model-generation requests. New providers should have a read-only data source, bounded subprocess execution, and offline tests. Provider schema changes should be reflected in documentation and the changelog.

Contributions are licensed under the project's MIT license.
