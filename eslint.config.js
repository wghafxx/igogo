const path = require("path");
const frontend = require("./frontend/eslint.config.js");

module.exports = frontend.map((cfg) => ({
  ...cfg,
  ...(cfg.files ? { files: cfg.files.map((f) => path.posix.join("frontend", f)) } : {}),
  ...(cfg.ignores ? { ignores: cfg.ignores.map((f) => path.posix.join("frontend", f)).concat(["backend/**", "tradebot/**", "scripts/**"]) } : {}),
}));
