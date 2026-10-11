# 🚀 File Splitter

A Python tool that downloads files from URLs, splits them into smaller chunks, and uploads those chunks to Google Drive.

Designed to run in Google Cloud Shell, with each user using their own Google OAuth credentials and Google Drive account.

## ✨ Features

- Download files directly from URLs.
- Detect HTTP Range support.
- Support Range-based and sequential downloading.
- Split large files into smaller chunks.
- Upload chunks directly to Google Drive.
- Retry interrupted downloads.
- Process files chunk by chunk instead of storing the entire file locally.

---

# 📋 Requirements

Before starting, make sure you have:

- A Google account.
- Access to Google Cloud Shell.
- A Google Cloud project.
- The Google Drive API enabled.
- Your own Google OAuth client credentials.
- An internet connection.

No local Python installation is required if you run the application entirely in Google Cloud Shell.

---

# 🛠️ Setup Guide

## Step 1: Open Google Cloud Shell

Visit:

https://shell.cloud.google.com/

Sign in with your Google account and open Cloud Shell.

Cloud Shell provides a browser-based terminal where you can run the application.

**Important:** Your Cloud Shell account and the Google account used to authorize Drive access can be different. Make sure you know which account you intend to use.

## Step 2: Create a Google Cloud project

1. Open the Google Cloud Console:

   https://console.cloud.google.com/

2. Sign in with your Google account.
3. Open the project selector at the top of the page.
4. Click **New Project**.
5. Enter a project name, such as `My File Splitter`.
6. Create the project.
7. Select the newly created project.

You may be asked to accept Google's terms or complete additional account setup.

## Step 3: Enable the Google Drive API

Open:

https://console.cloud.google.com/apis/library/drive.googleapis.com

Make sure your newly created project is selected.

Click **Enable**.

This allows your application to communicate with Google Drive through the API.

## Step 4: Configure Google OAuth

Open:

https://console.cloud.google.com/auth/overview

If the interface redirects you to Google's Google Auth Platform setup, follow the instructions there.

### 4.1 Configure the application

1. Open the branding or application information section.
2. Enter an application name, such as `File Splitter`.
3. Provide a support email if requested.
4. Enter a developer contact email.
5. Save the configuration.

The exact interface may vary depending on your Google Cloud project.

### 4.2 Configure the audience

Open the audience section.

For a personal project, choose the appropriate user type available for your Google account.

If the application is configured as **External** and remains in testing mode:

1. Add your own Google account as a test user.
2. Save the configuration.

Google may impose additional restrictions on applications that remain in testing mode.

### 4.3 Configure the required permissions

The application needs permission to upload files to Google Drive.

Your current script requests this OAuth scope:

`https://www.googleapis.com/auth/drive`

This grants broad Google Drive access.

Only authorize an application you trust. The application should eventually use the narrowest scope compatible with its functionality.

## Step 5: Create your OAuth client credentials

Open:

https://console.cloud.google.com/auth/clients

Alternatively, navigate to Google Auth Platform and open the Clients section.

1. Click **Create Client**.
2. Select the appropriate application type supported by the authentication flow.
3. Enter the requested configuration.
4. Create the OAuth client.
5. Download the client JSON file.

Save the downloaded file as:

`client_secret.json`

**Never upload this file to a public GitHub repository.**

Each user must create their own OAuth credentials. Do not share your private client file or authorization tokens with other users.

> Important: The current script uses a local-server OAuth flow. This may not work directly in Google Cloud Shell, where the browser and Python process operate in different environments. The authentication code must support the chosen remote authentication flow before the application can be used reliably.

## Step 6: Clone the repository

Return to Google Cloud Shell.

Run:

```bash
git clone https://github.com/YOUR_GITHUB_USERNAME/file-splitter.git
```

Replace `YOUR_GITHUB_USERNAME` with the GitHub username that owns the repository.

Enter the project directory:

```bash
cd file-splitter
```

## Step 7: Upload your OAuth credentials

In the Cloud Shell interface:

1. Open the three-dot menu.
2. Select **Upload**.
3. Choose your downloaded `client_secret.json`.
4. Make sure the file is uploaded into the project directory.

Verify that it exists:

```bash
ls -l client_secret.json
```

If your file has a different name, rename it:

```bash
mv YOUR_DOWNLOADED_FILENAME.json client_secret.json
```

Keep this file private.

## Step 8: Install the Python dependencies

Run:

```bash
python -m pip install --user -r requirements.txt
```

If your environment requires a virtual environment, create and activate one before installing dependencies.

Verify the Python installation:

```bash
python --version
```

## Step 9: Connect your Google Drive account

Run the application using the instructions in the Usage section.

When authentication begins:

1. Follow the authentication instructions displayed by the application.
2. Sign in to the Google account whose Drive you want to use.
3. Review the requested permissions.
4. Approve access only if you trust the application.

The application should save the resulting authorization token locally.

The token file is sensitive and must never be committed to GitHub.

**Note:** Authentication will not work reliably until the current local-server OAuth implementation has been adapted for Cloud Shell.

---

# 📥 Usage

Once setup and authentication are complete, run:

```bash
python now.py "DOWNLOAD_URL"
```

Replace `DOWNLOAD_URL` with the direct download URL of the file.

For example:

```bash
python now.py "https://example.com/archive.zip"
```

The example URL is illustrative; use an actual, accessible download URL.

## Chunk size

The current script uses a default chunk size of 250 MB.

You can enter a different chunk size when prompted.

Supported values:

- Minimum: 10 MB
- Default: 250 MB
- Maximum: 2048 MB

A 100 MB default can be configured by changing `DEFAULT_CHUNK_MB` in `now.py`.

## Download modes

### Range mode

If the source supports HTTP Range requests, the application can download the file in separate byte ranges.

### Sequential mode

If the source does not support Range requests, the application uses sequential downloading.

The current version automatically chooses Range mode when Range support is detected. If you want users to choose the mode manually, the program must be updated accordingly.

---

# 📂 Google Drive Output

The application uploads the generated chunks to Google Drive.

Each user should authorize their own Google account.

The current script contains a hardcoded destination folder ID:

`DRIVE_FOLDER_ID`

Before using the application with different accounts, configure this setting so each user can specify their own destination folder.

Do not assume that a folder ID from another user's Drive is accessible to your account.

---

# ⚠️ Important Limitations

## Google Cloud Shell

Google Cloud Shell has storage, usage, session-duration, and inactivity limits.

A running task may be interrupted if a session ends or the environment restarts.

## Temporary storage

The application uses a temporary directory named `temp_parts`.

Temporary files may be lost if the environment restarts.

## Download recovery

Recovery depends on source-server behavior.

Some sources do not support Range requests, and some download URLs expire.

Sequential recovery can require downloading and skipping previously received bytes, consuming additional bandwidth.

## Google Drive API

Google may impose API quotas, authentication restrictions, or other limits.

Successful uploads depend on available Drive storage and API access.

## File size

The script processes files in chunks, but this does not mean file sizes are unlimited.

Available disk space, source-server behavior, session duration, network reliability, and Drive API constraints all affect the maximum practical file size.

---

# 🔐 Security

Never commit the following files:

- `client_secret.json`
- `token.json`
- Other OAuth token files.
- Private keys.
- Passwords or API credentials.

The `.gitignore` file should exclude these files.

If credentials are accidentally exposed, revoke or rotate them immediately.

Only authorize Google Drive access for applications you trust.

---

# 🧹 Cleanup

Temporary files are stored in:

`temp_parts/`

Do not manually delete files while a download is in progress.

The application should clean up its temporary files after successful processing.

If a task is interrupted, inspect the temporary directory before removing any remaining files.

---

# 📄 License

MIT License
