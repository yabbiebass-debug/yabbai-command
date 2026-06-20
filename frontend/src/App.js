import React from 'react';
import { BrowserRouter, Routes, Route } from 'react-router-dom';
import { ToastProvider } from './context/ToastContext';
import Layout from './components/Layout';
import CommandCentre from './pages/CommandCentre';
import YabbaiApp from './pages/YabbaiApp';
import Launch from './pages/Launch';
import Payment from './pages/Payment';
import Mission from './pages/Mission';
import Wallet from './pages/Wallet';
import Withdraw from './pages/Withdraw';
import ApiPulse from './pages/ApiPulse';
import Basham from './pages/Basham';
import SideHustle from './pages/SideHustle';
import Promo from './pages/Promo';
import Settings from './pages/Settings';
import Analytics from './pages/Analytics';
import './index.css';

function App() {
  return (
    <ToastProvider>
      <BrowserRouter>
        <Routes>
          <Route element={<Layout />}>
            <Route path="/" element={<CommandCentre />} />
            <Route path="/yabbai" element={<YabbaiApp />} />
            <Route path="/launch" element={<Launch />} />
            <Route path="/payment" element={<Payment />} />
            <Route path="/mission" element={<Mission />} />
            <Route path="/wallet" element={<Wallet />} />
            <Route path="/withdraw" element={<Withdraw />} />
            <Route path="/api-pulse" element={<ApiPulse />} />
            <Route path="/basham" element={<Basham />} />
            <Route path="/side-hustle" element={<SideHustle />} />
            <Route path="/promo" element={<Promo />} />
            <Route path="/settings" element={<Settings />} />
            <Route path="/analytics" element={<Analytics />} />
          </Route>
        </Routes>
      </BrowserRouter>
    </ToastProvider>
  );
}

export default App;
