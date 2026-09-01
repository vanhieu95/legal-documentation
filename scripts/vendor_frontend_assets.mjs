import { createHash } from "node:crypto";
import { mkdir, readFile, writeFile } from "node:fs/promises";
import path from "node:path";
import process from "node:process";

const projectRoot = process.cwd();
const checkOnly = process.argv.includes("--check");
const packageManifest = JSON.parse(
  await readFile(path.join(projectRoot, "package.json"), "utf8"),
);
const assetDefinitions = [
  {
    package: "htmx.org",
    license: "BSD-2-Clause",
    source: "node_modules/htmx.org/dist/htmx.min.js",
    destination: "static/vendor/htmx/htmx.min.js",
  },
  {
    package: "@alpinejs/csp",
    license: "MIT",
    source: "node_modules/@alpinejs/csp/dist/cdn.min.js",
    destination: "static/vendor/alpine/alpine.csp.min.js",
  },
];

async function checksum(contents) {
  return `sha256:${createHash("sha256").update(contents).digest("hex")}`;
}

const assets = [];
for (const definition of assetDefinitions) {
  const installedManifest = JSON.parse(
    await readFile(
      path.join(projectRoot, "node_modules", definition.package, "package.json"),
      "utf8",
    ),
  );
  const pinnedVersion = packageManifest.devDependencies[definition.package];
  if (installedManifest.version !== pinnedVersion) {
    throw new Error(
      `${definition.package} is ${installedManifest.version}; expected lock pin ${pinnedVersion}.`,
    );
  }

  const sourceContents = await readFile(path.join(projectRoot, definition.source));
  assets.push({
    ...definition,
    version: installedManifest.version,
    checksum: await checksum(sourceContents),
  });
}

const vendorManifest = {
  schema: 1,
  generatedBy: "npm run assets:vendor",
  assets,
};
const serializedManifest = `${JSON.stringify(vendorManifest, null, 2)}\n`;
const manifestPath = path.join(projectRoot, "static/vendor/manifest.json");
const applicationSourcePath = path.join(projectRoot, "static_src/js/app.js");
const applicationDestinationPath = path.join(projectRoot, "static/js/app.js");

if (checkOnly) {
  const committedManifest = await readFile(manifestPath, "utf8");
  if (committedManifest !== serializedManifest) {
    throw new Error("Vendored asset manifest is stale. Run npm run assets:vendor.");
  }
  for (const asset of assets) {
    const destinationContents = await readFile(path.join(projectRoot, asset.destination));
    if ((await checksum(destinationContents)) !== asset.checksum) {
      throw new Error(`${asset.destination} does not match its locked package source.`);
    }
  }
  if (
    (await readFile(applicationSourcePath, "utf8")) !==
    (await readFile(applicationDestinationPath, "utf8"))
  ) {
    throw new Error("static/js/app.js is stale. Run npm run assets:vendor.");
  }
  console.log("Vendored frontend assets match their exact package pins and checksums.");
} else {
  for (const asset of assets) {
    const destinationPath = path.join(projectRoot, asset.destination);
    await mkdir(path.dirname(destinationPath), { recursive: true });
    await writeFile(destinationPath, await readFile(path.join(projectRoot, asset.source)));
  }
  await mkdir(path.dirname(manifestPath), { recursive: true });
  await writeFile(manifestPath, serializedManifest, "utf8");
  await mkdir(path.dirname(applicationDestinationPath), { recursive: true });
  await writeFile(applicationDestinationPath, await readFile(applicationSourcePath));
  console.log("Vendored exact frontend assets and wrote static/vendor/manifest.json.");
}
