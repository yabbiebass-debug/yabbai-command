import React from 'react';
import { BrowserRouter, Routes, Route } from 'react-router-dom';
import { ToastProvider } from './context/ToastContext';
import Layout from './components/Layout';
import ProtectedRoute from './components/ProtectedRoute';
import CommandCentre from './pages/CommandCentre';
import YabbaiApp from './pages/YabbaiApp';
import Launch from './pages/Launch';
import Payment from './pages/Payment';
import Mission from './pages/Mission';
import Withdraw from './pages/Withdraw';
import ApiPulse from './pages/ApiPulse';
import Basham from './pages/Basham';
import SideHustle from './pages/SideHustle';
import Promo from './pages/Promo';
import Settings from './pages/Settings';
import Analytics from './pages/Analytics';
import FaucetPayout from './pages/FaucetPayout';
import './index.css';

function App() {
  return (
    <ToastProvider>
      <BrowserRouter>
        <ProtectedRoute>
          <Routes>
            <Route element={<Layout />}>
              <Route path="/" element={<CommandCentre />} />
              <Route path="/yabbai" element={<YabbaiApp />} />
              <Route path="/launch" element={<Launch />} />
              <Route path="/payment" element={<Payment />} />
              <Route path="/mission" element={<Mission />} />
              <Route path="/withdraw" element={<Withdraw />} />
              <Route path="/api-pulse" element={<ApiPulse />} />
              <Route path="/basham" element={<Basham />} />
              <Route path="/side-hustle" element={<SideHustle />} />
              <Route path="/promo" element={<Promo />} />
              <Route path="/settings" element={<Settings />} />
              <Route path="/analytics" element={<Analytics />} />
              {/* Director only. This route is inside ProtectedRoute and is never
                  compiled into the holders build, which has no router at all. */}
              <Route path="/faucet" element={<FaucetPayout />} />
            </Route>
          </Routes>
        </ProtectedRoute>
      </BrowserRouter>
    </ToastProvider>
  );
}

export default App;
