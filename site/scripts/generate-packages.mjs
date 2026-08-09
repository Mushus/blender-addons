import { mkdir, readFile, writeFile } from 'node:fs/promises';
import path from 'node:path';
import { fileURLToPath, pathToFileURL } from 'node:url';

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const SITE_ROOT = path.resolve(__dirname, '..');
const REPO_ROOT = path.resolve(SITE_ROOT, '..');
const PACKAGES_CATALOG = path.join(REPO_ROOT, 'release', 'packages.json');
const OUTPUT = path.join(SITE_ROOT, 'src', 'data', 'packages.json');
const INDEX_OUTPUT = path.join(SITE_ROOT, 'public', 'index.json');
const REPOSITORY_URL =
  'https://mushus.github.io/blender-addons/index.json';

/**
 * @param {string} url
 * @returns {Promise<any>}
 */
async function getJson(url) {
  const token = process.env.GITHUB_TOKEN;
  /** @type {Record<string, string>} */
  const headers = {
    Accept: 'application/vnd.github+json',
    'User-Agent': 'blender-addons-site',
  };
  if (token) {
    headers.Authorization = `Bearer ${token}`;
  }
  const response = await fetch(url, { headers });
  if (!response.ok) {
    throw new Error(`GET ${url} failed: ${response.status} ${response.statusText}`);
  }
  return response.json();
}

/**
 * @param {string} content
 * @param {string} key
 * @returns {unknown}
 */
function readBlInfoValue(content, key) {
  const stringMatch = content.match(
    new RegExp(`"${key}"\\s*:\\s*"([^"]*)"`, 'm'),
  );
  if (stringMatch) {
    return stringMatch[1];
  }
  const tupleMatch = content.match(
    new RegExp(`"${key}"\\s*:\\s*\\(([^)]*)\\)`, 'm'),
  );
  if (tupleMatch) {
    return tupleMatch[1]
      .split(',')
      .map((part) => part.trim())
      .filter(Boolean)
      .map((part) => Number(part));
  }
  throw new Error(`bl_info["${key}"] not found`);
}

/**
 * @param {unknown} value
 * @returns {string}
 */
function formatVersion(value) {
  if (!Array.isArray(value) || value.length === 0) {
    throw new Error(`invalid version tuple: ${JSON.stringify(value)}`);
  }
  if (value.some((part) => typeof part !== 'number' || Number.isNaN(part))) {
    throw new Error(`invalid version tuple: ${JSON.stringify(value)}`);
  }
  return value.join('.');
}

/**
 * @returns {Promise<{ catalog: any, packageIds: string[] }>}
 */
async function loadCatalog() {
  const catalog = JSON.parse(await readFile(PACKAGES_CATALOG, 'utf8'));
  const packages = catalog.packages;
  if (!Array.isArray(packages) || packages.length === 0) {
    throw new Error(`${PACKAGES_CATALOG} has no packages`);
  }
  return {
    catalog,
    packageIds: packages.map((pkg) => pkg.id),
  };
}

/**
 * @param {any} catalog
 * @param {string[]} packageIds
 */
async function loadLocalPackages(catalog, packageIds) {
  const packageIdSet = new Set(packageIds);
  /** @type {Record<string, any>} */
  const latest = {};
  for (const pkg of catalog.packages) {
    if (!packageIdSet.has(pkg.id)) {
      continue;
    }
    const initPath = path.join(REPO_ROOT, pkg.source, '__init__.py');
    const content = await readFile(initPath, 'utf8');
    latest[pkg.id] = {
      id: pkg.id,
      name: readBlInfoValue(content, 'name'),
      group_id: pkg.group_id,
      group_label: pkg.group_label,
      version: formatVersion(readBlInfoValue(content, 'version')),
      blender_target: formatVersion(readBlInfoValue(content, 'blender')),
      url: null,
      doc_link: `/addons/${pkg.id.replaceAll('_', '-')}/`,
    };
  }
  for (const packageId of packageIds) {
    if (!(packageId in latest)) {
      throw new Error(`local package metadata missing for ${packageId}`);
    }
  }
  return latest;
}

/**
 * @param {string} repository
 * @param {string[]} packageIds
 */
async function loadReleasePackages(repository, packageIds) {
  const packageIdSet = new Set(packageIds);
  /** @type {Record<string, any>} */
  const latest = {};
  /** @type {{ version: string, url: string | null } | null} */
  let suite = null;

  const releases = await getJson(
    `https://api.github.com/repos/${repository}/releases?per_page=100`,
  );
  if (!Array.isArray(releases)) {
    throw new Error('GitHub releases response is not an array');
  }

  for (const release of releases) {
    if (release.draft) {
      continue;
    }
    const assets = release.assets ?? [];
    const manifestAsset = assets.find(
      (asset) => asset.name === 'release-manifest.json',
    );
    if (!manifestAsset) {
      continue;
    }

    const manifest = await getJson(manifestAsset.browser_download_url);
    if (manifest?.suite?.file && !suite) {
      const suiteAsset = assets.find(
        (asset) => asset.name === manifest.suite.file,
      );
      suite = {
        version: manifest.generated_at ?? '',
        url: suiteAsset?.browser_download_url ?? null,
      };
    }

    for (const entry of manifest.packages ?? []) {
      if (
        !packageIdSet.has(entry.id) ||
        !entry.file ||
        entry.id in latest
      ) {
        continue;
      }
      const asset = assets.find((item) => item.name === entry.file);
      latest[entry.id] = {
        ...entry,
        url: asset?.browser_download_url ?? null,
        doc_link: `/addons/${entry.id.replaceAll('_', '-')}/`,
      };
    }
  }

  return { latest, suite };
}

/**
 * @param {Record<string, any>} fromReleases
 * @param {string[]} packageIds
 */
function buildExtensionsIndex(fromReleases, packageIds) {
  /** @type {any[]} */
  const data = [];
  for (const packageId of packageIds) {
    const published = fromReleases[packageId];
    const extension = published?.extension;
    const archiveUrl = published?.url;
    if (!extension || !archiveUrl) {
      continue;
    }
    if (
      typeof extension.archive_size !== 'number' ||
      typeof extension.archive_hash !== 'string' ||
      !extension.archive_hash.startsWith('sha256:')
    ) {
      throw new Error(
        `extension listing for ${packageId} is missing archive_size/archive_hash`
      );
    }
    data.push({
      ...extension,
      archive_url: archiveUrl,
    });
  }
  return {
    version: 'v1',
    blocklist: [],
    data,
  };
}

export async function generatePackages() {
  const repository =
    process.env.GITHUB_REPOSITORY ?? 'Mushus/blender-addons';
  const { catalog, packageIds } = await loadCatalog();
  const local = await loadLocalPackages(catalog, packageIds);
  const { latest: fromReleases, suite } = await loadReleasePackages(
    repository,
    packageIds,
  );

  const packages = packageIds.map((packageId) => {
    const published = fromReleases[packageId];
    if (!published) {
      return local[packageId];
    }
    return {
      ...local[packageId],
      ...published,
      group_id: local[packageId].group_id,
      group_label: local[packageId].group_label,
      doc_link: local[packageId].doc_link,
    };
  });

  const data = {
    packages,
    suite,
    extensions_repository_url: REPOSITORY_URL,
  };
  await mkdir(path.dirname(OUTPUT), { recursive: true });
  await writeFile(OUTPUT, `${JSON.stringify(data, null, 2)}\n`, 'utf8');
  console.log(`Generated ${OUTPUT}`);

  const index = buildExtensionsIndex(fromReleases, packageIds);
  await mkdir(path.dirname(INDEX_OUTPUT), { recursive: true });
  await writeFile(INDEX_OUTPUT, `${JSON.stringify(index, null, 2)}\n`, 'utf8');
  console.log(
    `Generated ${INDEX_OUTPUT} (${index.data.length} extension(s))`
  );
  return data;
}

const isDirectRun =
  Boolean(process.argv[1]) &&
  import.meta.url === pathToFileURL(path.resolve(process.argv[1])).href;

if (isDirectRun) {
  generatePackages().catch((error) => {
    console.error(error);
    process.exit(1);
  });
}
