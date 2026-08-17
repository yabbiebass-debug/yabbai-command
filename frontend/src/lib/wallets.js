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

function addWallet(wallet) {
  if (!wallet?.name) return;
  const chains = wallet.chains || [];
  // Some builds report chains only after connecting, so accept a wallet that
  // exposes Solana features even when its chain list is still empty.
  const solanaish =
    chains.some((c) => String(c).startsWith('solana:')) ||
    Object.keys(wallet.features || {}).some((f) => f.startsWith('solana:'));
  if (solanaish) _registry.set(wallet.name, wallet);
}

/**
 * The object the Wallet Standard requires an app to publish.
 *
 * This is the part that was missing and it broke every extension on the page.
 * The app-ready event MUST be a CustomEvent whose `detail` is this API, because
 * extensions destructure it on arrival:
 *
 *     ({ register }) => register(theirWallet)
 *
 * Dispatching a bare `new Event(...)` leaves `detail` undefined, so that
 * destructure throws inside the extension's own injected script — which is why
 * the console filled with "Cannot destructure property 'register' of
 * 'undefined'" traced to solana.js, inpage.js and injected.js rather than to
 * anything in this file. Each extension threw, registered nothing, and wallet
 * detection silently found zero wallets.
 */
function standardApi() {
  return {
    register: (...wallets) => {
      wallets.forEach(addWallet);
      return () => {}; // unregister handle; nothing to tear down here
    },
  };
}

function startListening() {
  if (_listening || typeof window === 'undefined') return;
  _listening = true;

  const api = standardApi();

  try {
    window.addEventListener(STANDARD_EVENT, (event) => {
      const detail = event?.detail;
      // Spec shape: detail is a callback the wallet wants handed the API.
      if (typeof detail === 'function') {
        try { detail(api); } catch { /* one bad extension must not stop others */ }
        return;
      }
      // Older builds pass the wallet object straight through.
      addWallet(detail?.wallet || detail);
    });

    const announce = () => {
      try {
        window.dispatchEvent(new CustomEvent(APP_READY, { detail: api }));
      } catch { /* ignore */ }
    };

    // Wallets already present re-announce when the app declares itself ready.
    announce();
    // Some extensions inject late; ask again a few times, then stop. This is
    // bounded deliberately — an unbounded poll re-runs every extension's
    // registration handler forever.
    [150, 600, 1500, 3000].forEach((ms) => setTimeout(announce, ms));
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

  // Jupiter's browser extension. It registers via the Wallet Standard like the
  // others; this is the direct handle as a fallback.
  push('Jupiter', window.jupiter?.solana || window.Jupiter?.solana || null);

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

/**
 * Sign and submit a Jupiter-built swap transaction.
 *
 * The transaction arrives unsigned from the server and is inert until this
 * wallet signs it. The wallet displays the amounts and the counterparty before
 * the user accepts — that prompt, not this code, is the thing protecting them.
 * Read it before approving.
 *
 * Prefers signAndSendTransaction so the wallet submits through its own RPC,
 * which usually lands more reliably and, for Jupiter Wallet, keeps its MEV
 * protection in the path.
 */
export async function signAndSendTransaction(entry, base64Tx) {
  const raw = Uint8Array.from(window.atob(base64Tx), (c) => c.charCodeAt(0));

  if (entry?.standard) {
    const features = entry.standard.features || {};
    const account = entry.standard.accounts?.[0];
    if (!account) throw new Error(`${entry.name} is not connected`);

    const sendFeature = features['solana:signAndSendTransaction'];
    if (sendFeature?.signAndSendTransaction) {
      // The Wallet Standard takes the serialised bytes directly. Send the chain
      // the wallet itself reports: some say solana:mainnet, others mainnet-beta,
      // and a mismatch is rejected.
      const chain =
        (entry.standard.chains || []).find((c) => SOLANA_CHAINS.includes(c)) ||
        'solana:mainnet';
      const [res] = await sendFeature.signAndSendTransaction({
        account,
        transaction: raw,
        chain,
      });
      if (!res?.signature) throw new Error('wallet returned no signature');
      return bs58FromBytes(res.signature);
    }
    throw new Error(
      `${entry.name} cannot submit transactions from this page. Use the Jupiter link instead.`
    );
  }

  const provider = entry?.provider;
  if (provider?.signAndSendTransaction) {
    // Injected providers take a web3.js transaction object, not bytes — they
    // call .serialize() on whatever they are given, so bytes fail with
    // "serialize is not a function". Jupiter builds versioned transactions;
    // fall back to the legacy format for anything that is not.
    const tx = await deserializeTransaction(raw);
    const res = await provider.signAndSendTransaction(tx);
    const sig = res?.signature || res;
    if (!sig) throw new Error('wallet returned no signature');
    return typeof sig === 'string' ? sig : bs58FromBytes(sig);
  }

  throw new Error(
    `${entry?.name || 'wallet'} cannot submit transactions. Use the Jupiter link instead.`
  );
}

/**
 * Bytes to a web3.js transaction object.
 *
 * Imported dynamically so web3.js stays out of the public holders bundle, which
 * has no signing path and must not carry one.
 */
async function deserializeTransaction(raw) {
  const web3 = await import('@solana/web3.js');
  try {
    return web3.VersionedTransaction.deserialize(raw);
  } catch {
    return web3.Transaction.from(raw);
  }
}

const B58 = '123456789ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz';

function bs58FromBytes(bytes) {
  const arr = bytes instanceof Uint8Array ? bytes : new Uint8Array(bytes);
  let digits = [0];
  for (let i = 0; i < arr.length; i += 1) {
    let carry = arr[i];
    for (let j = 0; j < digits.length; j += 1) {
      carry += digits[j] << 8;
      digits[j] = carry % 58;
      carry = (carry / 58) | 0;
    }
    while (carry > 0) {
      digits.push(carry % 58);
      carry = (carry / 58) | 0;
    }
  }
  let out = '';
  for (let i = 0; arr[i] === 0 && i < arr.length - 1; i += 1) out += '1';
  for (let i = digits.length - 1; i >= 0; i -= 1) out += B58[digits[i]];
  return out;
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
