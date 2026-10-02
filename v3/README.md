# V3 Direct Upload Frontend

This is the replacement upload architecture for large manufacturing files.

Flow: browser -> object storage -> processing backend -> dashboard.

The browser must upload directly to object storage using a short-lived presigned PUT URL. The 30-100 MB file body must not pass through Streamlit or a serverless function.

## Deployment
Deploy `v3/` as a static frontend. Connect `/api/upload-url` to an R2/S3-compatible presigning service. Configure CORS for the frontend origin.

## Security
Use random object keys, short-lived signed URLs, MIME/extension allow-listing, max-size enforcement, and automatic deletion/retention rules.

The existing Python analytics engine can then read the stored object and generate the executive dashboard/report.
