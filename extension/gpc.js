// Global Privacy Control: tells the page's own scripts "don't sell or share my data", alongside the Sec-GPC
// header the extension adds to every request. Only registered while the switch is on.
try {
  Object.defineProperty(Navigator.prototype, "globalPrivacyControl", { get: () => true, configurable: true, enumerable: true });
} catch { /* already defined by the browser */ }
