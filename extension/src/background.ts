/**
 * Service worker: the only job here is the Alt+U keyboard shortcut (see manifest.json's
 * "commands"). Clicking the toolbar icon opens the popup directly (manifest.json's
 * "action.default_popup"), which injects content.js itself — see src/popup/popup.ts — so this
 * file has nothing to do with that path.
 *
 * Invoking a declared command grants `activeTab` for the active tab for this call, the same way
 * clicking the toolbar icon does, which is what lets `chrome.scripting.executeScript` below run
 * without the extension ever declaring a host permission for the pages it works on.
 */

chrome.commands.onCommand.addListener((command) => {
  if (command !== 'unwind-page') return;
  chrome.tabs.query({ active: true, currentWindow: true }, (tabs) => {
    const tab = tabs[0];
    if (!tab?.id) return;
    void chrome.scripting.executeScript({ target: { tabId: tab.id }, files: ['content.js'] });
  });
});
