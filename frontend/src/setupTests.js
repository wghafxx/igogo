// Browser APIs provided by modern browsers but not CRA's older jsdom.
const { TextEncoder, TextDecoder } = require("util");
global.TextEncoder = TextEncoder;
global.TextDecoder = TextDecoder;