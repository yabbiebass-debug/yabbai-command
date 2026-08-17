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

// Wallets announce themselves asynchronously and at different times, so the
// registry is accumulated once at module level and kept, rather than rebuilt on
// each scan. A single snapshot taken too early finds nothing.
const _registry = new Map();
let _listening = false;

function startListening() {
  if (_listening || typeof window === 'undefined') return;
  _listening = true;
  const register = (event) => {
    const wallet = event?.detail?.wallet || event?.detail;
    if (!wallet?.name) return;
    const chains = wallet.chains || [];
    // Some builds report chains only after connecting, so accept a wallet that
    // exposes Solana features even when its chain list is still empty.
    const solanaish =
      chains.some((c) => String(c).startsWith('solana:')) ||
      Object.keys(wallet.features || {}).some((f) => f.startsWith('solana:'));
    if (solanaish) _registry.set(wallet.name, wallet);
  };
  try {
    window.addEventListener(STANDARD_EVENT, register);
    // Wallets already registered re-announce when the app declares itself ready.
    window.dispatchEvent(new Event(APP_READY));
    // Some extensions inject late; ask again a few times.
    [150, 600, 1500, 3000].forEach((ms) =>
      setTimeout(() => {
        try { window.dispatchEvent(new Event(APP_READY)); } catch { /* ignore */ }
      }, ms)
    );
  } catch {
    /* registry unavailable; globals below still apply */
  }
}

/** Wallets discovered via the Wallet Standard registry. */
function standardWallets() {
  startListening();
  return Array.from(_registry.values());
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

  // MetaMask exposes Solana through the Wallet Standard, so it normally arrives
  // via the registry. These are direct handles some builds also expose.
  push('MetaMask', window.metamask?.solana || window.ethereum?.solana || null);

  // A generic provider that is not one of the above.
  if (window.solana && !window.solana.isPhantom && !out.some((p) => p.provider === window.solana)) {
    push(window.solana.isSolflare ? 'Solflare' : 'Solana Wallet', window.solana);
  }
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

/**
 * Sign a message to prove control of the wallet.
 *
 * This is a signature over text, not a transaction. It authorises nothing, moves
 * nothing and costs nothing — a wallet cannot be drained by signing here. The
 * message is issued by the server and carries a single-use nonce and the domain,
 * so a signature cannot be replayed or captured by another site and reused.
 */
export async function signMessage(entry, message) {
  const bytes = new TextEncoder().encode(message);

  if (entry?.standard) {
    const feature = entry.standard.features?.['solana:signMessage'];
    if (!feature?.signMessage) {
      throw new Error(`${entry.name} cannot sign messages`);
    }
    const account = entry.standard.accounts?.[0];
    if (!account) throw new Error(`${entry.name} is not connected`);
    const [result] = await feature.signMessage({ account, message: bytes });
    if (!result?.signature) throw new Error('wallet returned no signature');
    return toBase64(result.signature);
  }

  const provider = entry?.provider;
  if (!provider?.signMessage) {
    throw new Error(`${entry?.name || 'wallet'} cannot sign messages`);
  }
  const res = await provider.signMessage(bytes, 'utf8');
  const sig = res?.signature || res;
  if (!sig) throw new Error('wallet returned no signature');
  return toBase64(sig);
}

function toBase64(bytes) {
  const arr = bytes instanceof Uint8Array ? bytes : new Uint8Array(bytes);
  let binary = '';
  arr.forEach((b) => { binary += String.fromCharCode(b); });
  return window.btoa(binary);
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
