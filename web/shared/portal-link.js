/** Rewrite owner-portal links for local/Fly same-origin vs marketing .com hosts. */
(function () {
  var PORTAL = "https://testnet.syntrends.com/owners/";
  var host = (location.hostname || "").toLowerCase();
  var sameOrigin =
    host === "localhost" ||
    host === "127.0.0.1" ||
    host === "::1" ||
    host === "testnet.syntrends.com" ||
    host.indexOf("fly.dev") !== -1;
  var href = sameOrigin ? "/owners/" : PORTAL;
  var nodes = document.querySelectorAll("a[data-portal]");
  for (var i = 0; i < nodes.length; i++) {
    nodes[i].setAttribute("href", href);
  }
})();
