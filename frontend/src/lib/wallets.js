/**
 * Solana wallet detection and connection.
 *
 * Uses the Wallet Standard registry rather than sniffing window globals. That is
 * how MetaMask exposes its Solana support, alongside Phantom, Solflare and
 * Backpack, so one code path finds all of them and any wallet added later works
 * without a change here. Known globals are still checked as a fallback for older
 * extension builds that predate the standard.
 *
 * What connecting does and does not do
 * ------------------------------------
 * Connecting asks the extension for a public key. The site never sees a private
 * key or a seed phrase, and cannot obtain one — the extension holds them and
 * exposes only a signing method that prompts the user for every transaction.
 * Nothing here signs anything; it reads addresses so balances can be shown.
 *
 * Spending still goes through the existing sweep path, which builds the
 * transaction in the browser, has the user's own wallet sign it, and only allows
 * destinations on the server's hardcoded allowlist.
 */

const STANDARD_EVENT = 'wallet-standard:register-wallet';
const APP_READY = 'wallet-standard:app-ready';

const SOLANA_CHAINS = ['solana:mainnet', 'solana:mainnet-beta'];

/** Wallets discovered via the Wallet Standard registry. */
function standardWallets() {
  const found = [];
  const register = ({ wallet }) => {
    if (!wallet) return;
    const chains = wallet.chains || [];
    const supportsSolana = chains.some((c) => String(c).startsWith('solana:'));
    if (!supportsSolana) return;
    if (found.some((w) => w.name === wallet.name)) return;
    found.push(wallet);
  };

  try {
    window.addEventListener(STANDARD_EVENT, (event) => register(event.detail || {}));
    // Wallets that registered before we listened re-announce on this event.
    window.dispatchEvent(new Event(APP_READY));
  } catch {
    /* registry unavailable; fall back to globals below */
  }
  return found;
}

/** Older extensions that expose a global instead of registering. */
function legacyProviders() {
  const out = [];
  const push = (name, provider, icon) => {
    if (provider && !out.some((p) => p.name === name)) {
      out.push({ name, provider, icon, legacy: true });
    }
  };
  if (typeof window === 'undefined') return out;

  push('Phantom', window.phantom?.solana || (window.solana?.isPhantom ? window.solana : null));
  push('Solflare', window.solflare?.isSolflare ? window.solflare : null);
  push('Backpack', window.backpack?.isBackpack ? window.backpack : null);
  // MetaMask's Solana support registers via the standard; this catches builds
  // that also expose a direct handle.
  push('MetaMask', window.phantom?.solana === undefined ? window.metamask?.solana : null);
  return out;
}

/** Every Solana wallet available in this browser. */
export function detectWallets() {
  const standard = standardWallets().map((w) => ({
    name: w.name,
    icon: w.icon,
    standard: w,
  }));
  const legacy = legacyProviders().filter(
    (l) => !standard.some((s) => s.name.toLowerCase() === l.name.toLowerCase())
  );
  return [...standard, ...legacy];
}

/** Connect and return { name, address }. Throws if the user declines. */
export async function connectWallet(entry) {
  if (!entry) throw new Error('No wallet selected');

  // Wallet Standard path.
  if (entry.standard) {
    const feature = entry.standard.features?.['standard:connect'];
    if (!feature?.connect) throw new Error(`${entry.name} does not support connect`);
    const result = await feature.connect();
    const account = (result?.accounts || entry.standard.accounts || [])[0];
    if (!account) throw new Error(`${entry.name} returned no account`);
    return { name: entry.name, address: account.address, account };
  }

  // Legacy global path.
  const provider = entry.provider;
  const res = await provider.connect();
  const key = res?.publicKey || provider.publicKey;
  if (!key) throw new Error(`${entry.name} returned no public key`);
  return { name: entry.name, address: key.toString() };
}

export async function disconnectWallet(entry) {
  try {
    if (entry?.standard) {
      await entry.standard.features?.['standard:disconnect']?.disconnect?.();
    } else {
      await entry?.provider?.disconnect?.();
    }
  } catch {
    /* disconnect is best-effort; the UI clears state regardless */
  }
}

/** Which chains a wallet reports. Useful for showing why one is unusable. */
export function walletChains(entry) {
  if (entry?.standard?.chains) {
    return entry.standard.chains.filter((c) => String(c).startsWith('solana:'));
  }
  return SOLANA_CHAINS;
}
