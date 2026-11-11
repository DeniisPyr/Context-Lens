# Deployment and troubleshooting

[Back to the README](../README.md)

The Docker quick start publishes the app on your own machine. These notes cover access, deployment, and current limitations.

## Security

The app holds private documents and spends Gemini credits on every upload and question, so:

- **Login:**
  - With `ACCESS_PASSWORD` set, the dataset, document, and question routes need a session. The health check and session routes remain open so a visitor can check the app and log in.
  - Logging in sets a cookie that lasts 12 hours. JavaScript can't read it (HttpOnly), and the browser sends it only to this site's `/api` (SameSite=Strict).
  - The cookie is signed with a key derived from the password with scrypt, so a stolen cookie doesn't make the password quick to guess. Changing the password ends every session.
  - The server keeps no sessions, so a restart logs no one out.
- **nginx, in the Docker setup:**
  - It refuses a request over 2 MB before the backend writes it to disk.
  - Each address gets 5 login attempts a minute, 10 questions a minute, and 30 uploads a minute after a burst of 100, the size of a full dataset.
  - It sends a strict Content-Security-Policy, and headers that stop the page from being framed or a response from being sniffed as another type.
  - It doesn't pass on the backend's interactive API docs.
- **Containers:** both run as unprivileged users without Linux capabilities, and an `.env` file never goes into an image. Base images are pinned by digest.
- **Logs:** document text, quotes, questions and Gemini's answers are never logged. Neither are pypdf's messages, which can quote a PDF.
- **Before serving it to others:** put it behind a proxy that adds HTTPS, set `SECURE_COOKIES=true`, and follow the checklist at the top of `frontend/nginx/default.conf`.

## Limitations and next steps

- **Answers in two places.** One search for the whole question often finds only one of them, which is the main reason search scores below whole documents. Searching once for each part of the question, or again with what the first answer names, should help. The evaluation can show how much.
- **Only the quotes are checked.** The check proves that each quote is in the document, not that the answer says what its quotes say.
- **Line numbers in quotes.** Once in 233 runs, Gemini copied a line's number from the prompt into its quote, and the check rejected a right answer. Removing such a number before the check should keep those answers.
- **A side effect of clarifying questions.** One question that needs two documents was answered right in 2 of 3 runs before Gemini could ask back, and got "not found" in all 3 after. Running both instructions on that question side by side would show whether the new one is the cause.
- **PDFs.** There's no OCR, so scanned PDFs can't be read, and columns and tables come out in the order pypdf reads them.
- **Questions are kept in the page.** The cards of a session live in the browser's memory, so a reload or a logout clears them.
- **One password for everyone.** Everyone who logs in sees every dataset. Sharing it between people would need user accounts, with datasets of their own.
- **One machine.** The Docker setup is published on this machine only. To serve it to others, it needs HTTPS in front, `SECURE_COOKIES=true`, and nginx set to see each client's real address for the rate limits. The checklist at the top of `frontend/nginx/default.conf` lists these steps and the rest.
- **Gemini's errors.** When the Gemini account runs out of prepaid credits, the app says only that Gemini could not answer the question, or could not index the document. The reason is only in the backend's log.
