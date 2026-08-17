import React from 'react';
import Holders from './pages/Holders';
import JoinPanel from './components/JoinPanel';
import FaucetClaim from './components/FaucetClaim';
import './index.css';

/**
 * Public holder view — the entire application for holders.yabbai.network.
 *
 * Deliberately minimal. There is no router, no ProtectedRoute, no Layout with
 * admin navigation, no Settings, no Withdraw, and no auth code of any kind.
 * Admin functionality is not hidden from this build; it is never compiled into
 * it, so a bug here cannot expose a surface that does not exist.
 *
 * WALLET CODE, AND WHY IT IS NOW HERE
 *
 * This build previously contained no wallet code at all. FaucetClaim adds
 * exactly one capability: signMessage, used to prove a claimer holds the
 * address they are claiming for.
 *
 * That is a narrower thing than it sounds. A signed message is a signature over
 * text — it authorises no transfer, grants no allowance, and cannot move a
 * lamport. signAndSendTransaction is NOT imported here and must not be; the
 * moment this build can submit a transaction, the isolation argument above
 * stops being true and a bug on the public page becomes a way to move value.
 *
 * Network calls remain credentials:'omit', so the .yabbai.network session
 * cookie still never reaches this origin.
 */
export default function HoldersApp() {
  // JoinPanel sits directly under the statistics, deliberately. A visitor reads
  // holder count and concentration first and the buy link second — the ordering
  // is the honesty. Reversing it would make this a funnel with data attached
  // rather than data with a next step.
  return (
    <>
      <Holders />
      <JoinPanel />
      <FaucetClaim />
    </>
  );
}
