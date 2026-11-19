"""Optional native smoke test with the installed .NET SDK, Node, React and the live dashboard.

Run python tests/windows_pilot.py on Windows. The React example uses npm's registry.
"""

import json
import os
import shutil
import unittest
from pathlib import Path

from test_global_factory import GlobalFactoryTest


@unittest.skipUnless(os.name == "nt", "native Windows pilot")
class WindowsPilot(unittest.TestCase):
    setUp = GlobalFactoryTest.setUp
    app = GlobalFactoryTest.app
    run_cli = GlobalFactoryTest.run_cli
    factory = GlobalFactoryTest.factory
    local_job = GlobalFactoryTest.local_job
    registration = GlobalFactoryTest.registration

    def test_real_backend_frontend_gates_and_dashboard(self):
        backend = self.app("Backend")
        frontend = self.app("Frontend")
        sdk = self.run_cli(["dotnet", "--version"]).stdout.strip().split(".")[0]
        self.env.update(DOTNET_CLI_TELEMETRY_OPTOUT="1", DOTNET_NOLOGO="1",
                        DOTNET_CLI_HOME=str(self.temp / "dotnet"))
        (backend / "Backend.csproj").write_text(
            f'<Project Sdk="Microsoft.NET.Sdk"><PropertyGroup><TargetFramework>net{sdk}.0</TargetFramework>'
            '</PropertyGroup></Project>')
        (backend / "NuGet.Config").write_text('<configuration><packageSources><clear/></packageSources></configuration>')
        (backend / "Service.cs").write_text("public class Service { public int Value => 42; }")
        (backend / ".gitignore").write_text("bin/\nobj/\n")
        (frontend / ".gitignore").write_text("node_modules/\n")
        (frontend / "package.json").write_text(json.dumps({
            "name": "factory-pilot", "private": True, "scripts": {"check": "node --test ui.test.cjs"}}))
        (frontend / "ui.test.cjs").write_text(
            "const React = require('react'); const {renderToStaticMarkup} = require('react-dom/server');\n"
            "require('node:test')('renders the title', () => require('node:assert/strict').equal("
            "renderToStaticMarkup(React.createElement('h1', null, 'Orders')), '<h1>Orders</h1>'));\n")
        npm = shutil.which("npm.cmd")
        self.run_cli([npm, "install", "--no-audit", "--no-fund", "--ignore-scripts",
                      "react@19", "react-dom@19", "jsdom@28"], frontend)
        for app, command in [(backend, ["dotnet", "build", "Backend.csproj"]), (frontend, ["npm", "run", "check"])]:
            p = app / ".factory/project.json"
            cfg = json.loads(p.read_bytes())
            cfg["checks"]["windows"] = {"commands": [command]}
            p.write_text(json.dumps(cfg))
            self.run_cli(["git", "add", "."], app)
            self.run_cli(["git", "commit", "-qm", "configure real checks"], app)
            self.factory(app, "gate", "--preflight")
        (backend / "Service.cs").write_text("this is invalid C#")
        (frontend / "ui.test.cjs").write_text("require('node:assert/strict').fail('regression')")
        self.factory(backend, "gate", "--preflight", code=1)
        self.factory(frontend, "gate", "--preflight", code=1)
        for app in (backend, frontend):
            self.run_cli(["git", "restore", "."], app)
            self.local_job(app)
        link = self.factory(backend, "dashboard", "start").stdout.strip()
        record = self.registration(frontend)
        probe = frontend / "dashboard.cjs"
        probe.write_text("""const {JSDOM} = require('jsdom');
const assert = require('node:assert/strict');
const [url, project] = process.argv.slice(2);
async function load(location) {
  return JSDOM.fromURL(location, {runScripts: 'dangerously', beforeParse(window) {
    window.fetch = (path, options) => fetch(new URL(path, window.location), options);
  }});
}
async function until(predicate) {
  for (let attempt = 0; attempt < 100; attempt++) {
    if (predicate()) return;
    await new Promise(resolve => setTimeout(resolve, 50));
  }
  throw Error('Dashboard did not reach the expected state');
}
(async () => {
  const dom = await load(url);
  let directLink;
  try {
    const {document, Event} = dom.window;
    const cards = () => [...document.querySelectorAll('.project-name')];
    await until(() => cards().length === 2);
    assert.deepEqual(cards().map(c => c.textContent).sort(), ['Backend', 'Frontend']);
    const select = document.querySelector('#project-filter');
    assert.ok(select.textContent.includes('Backend · 1/1 active'));
    select.value = project;
    select.dispatchEvent(new Event('change'));
    await until(() => cards().length === 1);
    document.querySelector('.card').click();
    await until(() => document.querySelector('#d-doc').textContent.includes('Build feature'));
    assert.ok(document.querySelector('#d-num').textContent.startsWith('Frontend · 001-same-task'));
    directLink = dom.window.location.href;
    assert.equal(new URL(directLink).hash, '#' + project + '/001-same-task');
  } finally { dom.window.close(); }
  const reopened = await load(directLink);
  try {
    const doc = reopened.window.document;
    await until(() => doc.body.classList.contains('open') && doc.querySelector('#d-num').textContent.startsWith('Frontend'));
  } finally { reopened.window.close(); }
})().catch(error => { console.error(error); process.exitCode = 1; });
""", encoding="utf-8")
        self.run_cli(["node", probe, link, record["project_id"]], frontend)


if __name__ == "__main__":
    unittest.main(defaultTest="WindowsPilot", verbosity=2)
