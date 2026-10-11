// Screenshot Viewer — Scriptable script (no building/compiling needed)
//
// SETUP:
// 1. Install the free "Scriptable" app from the iOS App Store.
// 2. Open Scriptable, tap "+" to create a new script.
// 3. Delete the placeholder content and paste in this entire file.
// 4. Edit SERVER_URL and API_KEY below to match your deployed server.
// 5. Rename the script (top of screen) to something like "Screenshot".
// 6. Run it once to test it works.
// 7. To get a Home Screen icon, use the Shortcuts app (see ../README.md
//    for the exact steps) — current versions of Scriptable no longer
//    expose "Add to Home Screen" directly from the script list.
//    IMPORTANT: in the Shortcut, use the "Run Script in App" action, not
//    plain "Run Script" — otherwise Alert/QuickLook will fail with
//    "Alerts are not supported in Siri".

const SERVER_URL = "https://your-app-name.ondigitalocean.app"; // <-- EDIT ME
const API_KEY = "replace-with-the-same-secret-you-set-on-the-server"; // <-- EDIT ME

async function fetchScreenshot() {
  const req = new Request(`${SERVER_URL}/screenshot`);
  req.headers = { "X-API-Key": API_KEY };
  const image = await req.loadImage();
  if (req.response.statusCode !== 200) {
    throw new Error(`Server returned status ${req.response.statusCode}`);
  }
  return image;
}

async function showError(message) {
  const alert = new Alert();
  alert.title = "Couldn't load screenshot";
  alert.message = message;
  alert.addAction("OK");
  await alert.present();
}

async function main() {
  let image;
  try {
    image = await fetchScreenshot();
  } catch (e) {
    await showError(String(e));
    return;
  }

  // Full-screen native preview of the image before deciding what to do.
  await QuickLook.present(image, false);

  const alert = new Alert();
  alert.title = "Screenshot";
  alert.message = "What would you like to do?";
  alert.addAction("Copy to Clipboard");
  alert.addAction("Save to Photos");
  alert.addAction("Copy & Save");
  alert.addCancelAction("Cancel");

  const choice = await alert.present(); // 0, 1, 2, or -1 for cancel
  if (choice === -1) return;

  if (choice === 0 || choice === 2) {
    Pasteboard.copyImage(image);
  }
  if (choice === 1 || choice === 2) {
    Photos.save(image);
  }

  const done = new Alert();
  done.title = "Done";
  done.message =
    choice === 0 ? "Copied to clipboard." :
    choice === 1 ? "Saved to Photos." :
    "Copied to clipboard and saved to Photos.";
  done.addAction("OK");
  await done.present();
}

await main();
