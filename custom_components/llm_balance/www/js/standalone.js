/** 独立部署入口。 */

import { mountApp } from "./app.js";
import { standaloneBackend } from "./api.js";

mountApp(document.getElementById("app"), standaloneBackend());
