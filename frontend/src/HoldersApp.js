import React from 'react';
import Holders from './pages/Holders';
import './index.css';

/**
 * Public holder view — the entire application for holders.yabbai.network.
 *
 * Deliberately minimal. There is no router, no ProtectedRoute, no Layout with
 * admin navigation, no Settings, no Withdraw, no wallet adapter, and no auth code
 * of any kind. Admin functionality is not hidden from this build; it is never
 * compiled into it, so a bug here cannot expose a surface that does not exist.
 *
 * The only network calls it makes are to /api/public/*, with credentials omitted.
 */
export default function HoldersApp() {
  return <Holders />;
}
