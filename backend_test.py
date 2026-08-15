import requests
import sys
from datetime import datetime

# Get backend URL from frontend .env
BACKEND_URL = "https://yabbai-command.preview.emergentagent.com/api"

# Expected wallet addresses after fix
NEW_TREASURY_WALLET = "HTN1fvHwbzKiMwh9YXZEe3eooiMdoCAs3TweWdiSZV5i"
OLD_TREASURY_WALLET = "7dzgCA8G55VytZ8PS1b99rbbctzCgJbnEoBEYBnn15YR"
METAMASK_MAIN = "7ApE9ABS11vdQCSPiPikGHcMU2iF7sFqRdSQUX1cwD7Z"
JUPITER_MAIN = "49nBAJdaTSUyNo5Uepb8HSGXxjX26Pd4x5sJp8PaNoFz"

AUTHORIZED_WALLETS = {NEW_TREASURY_WALLET, METAMASK_MAIN, JUPITER_MAIN}

class WalletConfigTester:
    def __init__(self):
        self.tests_run = 0
        self.tests_passed = 0
        self.critical_issues = []
        self.warnings = []

    def run_test(self, name, test_func):
        """Run a single test"""
        self.tests_run += 1
        print(f"\n🔍 Testing {name}...")
        
        try:
            success, message = test_func()
            if success:
                self.tests_passed += 1
                print(f"✅ PASSED - {message}")
            else:
                print(f"❌ FAILED - {message}")
                self.critical_issues.append(f"{name}: {message}")
            return success
        except Exception as e:
            print(f"❌ FAILED - Error: {str(e)}")
            self.critical_issues.append(f"{name}: {str(e)}")
            return False

    def test_settings_api(self):
        """Test /api/settings returns correct treasury and main wallet"""
        try:
            response = requests.get(f"{BACKEND_URL}/settings", timeout=10)
            if response.status_code != 200:
                return False, f"Status {response.status_code}"
            
            data = response.json()
            treasury = data.get("treasury_wallet", "")
            main_wallet = data.get("main_wallet", "")
            
            print(f"   Treasury wallet: {treasury}")
            print(f"   Main wallet: {main_wallet}")
            
            issues = []
            
            # Check treasury wallet
            if treasury != NEW_TREASURY_WALLET:
                if treasury == OLD_TREASURY_WALLET:
                    issues.append(f"CRITICAL: Still using OLD treasury wallet {OLD_TREASURY_WALLET[:8]}...")
                else:
                    issues.append(f"Unknown treasury wallet: {treasury[:8]}...")
            
            # Check main wallet - CRITICAL BUG FIX
            if "TestWallet" in main_wallet:
                issues.append(f"CRITICAL: main_wallet still shows TestWallet123 instead of real METAMASK_MAIN")
            elif main_wallet != METAMASK_MAIN:
                issues.append(f"main_wallet is {main_wallet[:8]}... but should be METAMASK_MAIN ({METAMASK_MAIN[:8]}...)")
            
            if issues:
                return False, "\n   ".join(issues)
            
            return True, f"Treasury and main wallet correctly configured"
        except Exception as e:
            return False, str(e)

    def test_whitelist_validation(self):
        """Test /api/sweep/validate-destination for all 3 authorized wallets"""
        all_valid = True
        messages = []
        
        for wallet in AUTHORIZED_WALLETS:
            try:
                response = requests.get(
                    f"{BACKEND_URL}/sweep/validate-destination",
                    params={"address": wallet},
                    timeout=10
                )
                if response.status_code != 200:
                    all_valid = False
                    messages.append(f"{wallet[:8]}... returned {response.status_code}")
                    continue
                
                data = response.json()
                if not data.get("authorized"):
                    all_valid = False
                    messages.append(f"{wallet[:8]}... NOT authorized")
                else:
                    messages.append(f"{wallet[:8]}... ✓ authorized")
            except Exception as e:
                all_valid = False
                messages.append(f"{wallet[:8]}... error: {str(e)}")
        
        # Test OLD wallet should NOT be authorized
        try:
            response = requests.get(
                f"{BACKEND_URL}/sweep/validate-destination",
                params={"address": OLD_TREASURY_WALLET},
                timeout=10
            )
            data = response.json()
            if data.get("authorized"):
                all_valid = False
                messages.append(f"OLD wallet {OLD_TREASURY_WALLET[:8]}... is STILL authorized (should be removed)")
            else:
                messages.append(f"OLD wallet {OLD_TREASURY_WALLET[:8]}... correctly NOT authorized")
        except Exception as e:
            messages.append(f"OLD wallet check error: {str(e)}")
        
        return all_valid, "\n   ".join(messages)

    def test_treasury_snapshots(self):
        """Test /api/treasury-snapshots for old wallet data"""
        try:
            response = requests.get(f"{BACKEND_URL}/treasury-snapshots?limit=500", timeout=10)
            if response.status_code != 200:
                return False, f"Status {response.status_code}"
            
            snapshots = response.json()
            
            if not isinstance(snapshots, list):
                return False, "Invalid response format"
            
            print(f"   Total snapshots: {len(snapshots)}")
            
            # Check for old wallet snapshots
            old_wallet_snapshots = [s for s in snapshots if s.get("address", "").lower() == OLD_TREASURY_WALLET.lower()]
            new_wallet_snapshots = [s for s in snapshots if s.get("address", "").lower() == NEW_TREASURY_WALLET.lower()]
            
            print(f"   Old wallet snapshots: {len(old_wallet_snapshots)}")
            print(f"   New wallet snapshots: {len(new_wallet_snapshots)}")
            
            if old_wallet_snapshots:
                # Check if any have high balances (124.7 SOL issue)
                high_balance_snaps = [s for s in old_wallet_snapshots if s.get("balance_sol", 0) > 100]
                if high_balance_snaps:
                    return False, f"Found {len(high_balance_snaps)} old wallet snapshots with >100 SOL (fake historical data)"
                else:
                    self.warnings.append(f"Found {len(old_wallet_snapshots)} old wallet snapshots (should be deleted)")
                    return True, f"Old wallet snapshots exist but no high balances"
            
            return True, "No old wallet snapshots found (correctly cleaned)"
        except Exception as e:
            return False, str(e)

    def test_analytics_api(self):
        """Test /api/analytics for treasury balance"""
        try:
            response = requests.get(f"{BACKEND_URL}/analytics", timeout=10)
            if response.status_code != 200:
                return False, f"Status {response.status_code}"
            
            data = response.json()
            treasury_sol = data.get("latest_treasury_sol")
            
            print(f"   Latest treasury SOL: {treasury_sol}")
            
            # We expect 0 SOL for new wallet or None if no snapshots
            if treasury_sol is None:
                return True, "No treasury snapshots yet (expected for new wallet)"
            elif treasury_sol > 100:
                return False, f"Treasury shows {treasury_sol} SOL - likely old wallet data (124.7 SOL issue)"
            else:
                return True, f"Treasury balance: {treasury_sol} SOL (reasonable)"
        except Exception as e:
            return False, str(e)

    def test_live_treasury_balance(self):
        """Test live balance of NEW treasury wallet"""
        try:
            response = requests.get(
                f"{BACKEND_URL}/solana-balance",
                params={"owner": NEW_TREASURY_WALLET},
                timeout=15
            )
            if response.status_code != 200:
                return False, f"Status {response.status_code}"
            
            data = response.json()
            if not data.get("ok"):
                return False, f"Balance check failed: {data.get('error')}"
            
            sol_balance = data.get("sol", 0)
            print(f"   NEW treasury wallet live balance: {sol_balance} SOL")
            
            return True, f"Live balance: {sol_balance} SOL"
        except Exception as e:
            return False, str(e)

    def test_old_wallet_references(self):
        """Check if old wallet appears in any API responses"""
        endpoints = [
            "/settings",
            "/token-mint",
            "/transactions?limit=10",
        ]
        
        found_old_wallet = []
        
        for endpoint in endpoints:
            try:
                response = requests.get(f"{BACKEND_URL}{endpoint}", timeout=10)
                if response.status_code == 200:
                    text = response.text.lower()
                    if OLD_TREASURY_WALLET.lower() in text:
                        found_old_wallet.append(endpoint)
            except:
                pass
        
        if found_old_wallet:
            return False, f"Old wallet found in: {', '.join(found_old_wallet)}"
        return True, "No references to old wallet in API responses"

def main():
    print("=" * 70)
    print("YABBAI WALLET CONFIGURATION TEST")
    print("=" * 70)
    print(f"Backend URL: {BACKEND_URL}")
    print(f"NEW Treasury Wallet: {NEW_TREASURY_WALLET}")
    print(f"OLD Treasury Wallet: {OLD_TREASURY_WALLET} (should NOT appear)")
    print(f"Authorized Wallets: {len(AUTHORIZED_WALLETS)}")
    print("=" * 70)
    
    tester = WalletConfigTester()
    
    # Run all tests
    tester.run_test("Settings API - Treasury Wallet", tester.test_settings_api)
    tester.run_test("Whitelist Validation - All 3 Wallets", tester.test_whitelist_validation)
    tester.run_test("Treasury Snapshots - Old Data Check", tester.test_treasury_snapshots)
    tester.run_test("Analytics API - Treasury Balance", tester.test_analytics_api)
    tester.run_test("Live Treasury Balance - NEW Wallet", tester.test_live_treasury_balance)
    tester.run_test("Old Wallet References Check", tester.test_old_wallet_references)
    
    # Print summary
    print("\n" + "=" * 70)
    print("TEST SUMMARY")
    print("=" * 70)
    print(f"Tests Run: {tester.tests_run}")
    print(f"Tests Passed: {tester.tests_passed}")
    print(f"Tests Failed: {tester.tests_run - tester.tests_passed}")
    
    if tester.critical_issues:
        print("\n❌ CRITICAL ISSUES:")
        for issue in tester.critical_issues:
            print(f"  • {issue}")
    
    if tester.warnings:
        print("\n⚠️  WARNINGS:")
        for warning in tester.warnings:
            print(f"  • {warning}")
    
    if tester.tests_passed == tester.tests_run:
        print("\n✅ ALL TESTS PASSED - Wallet configuration is correct!")
        return 0
    else:
        print(f"\n❌ {tester.tests_run - tester.tests_passed} TESTS FAILED - Issues need to be fixed")
        return 1

if __name__ == "__main__":
    sys.exit(main())
