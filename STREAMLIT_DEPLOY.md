# Streamlit Community Cloud Deploy

## Included files
- `app.py`
- `requirements.txt`
- `packages.txt`
- `.streamlit/config.toml`

## Deploy steps
1. Push this folder to GitHub.
2. Open Streamlit Community Cloud.
3. Create a new app from the repository.
4. Set the main file path to `app.py`.
5. Deploy.

## Notes
- The app uses Selenium, so Chromium and chromedriver are required on Cloud.
- Runtime files such as recent search history and exported spreadsheets are stored in `runtime/`.
- `runtime/` is not meant to be committed.
