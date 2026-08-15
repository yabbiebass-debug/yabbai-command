import requests
import sys
from datetime import datetime

# Get backend URL from frontend .env
BACKEND_URL = "https://yabbai-command.preview.emergentagent.com/api"

class HubSSOTester:
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

    def test_auth_me_returns_401(self):
        """Test /api/auth/me returns 401 (not 503) when no auth provided"""
        try:
            response = requests.get(f"{BACKEND_URL}/auth/me", timeout=10)
            status = response.status_code
            
            print(f"   Status code: {status}")
            
            if status == 503:
                return False, "Returns 503 - HUB_AUTH_URL likely not loaded (import order issue)"
            elif status == 401:
                return True, "Returns 401 - HUB_AUTH_URL loaded correctly, auth check working"
            else:
                return False, f"Unexpected status {status} (expected 401)"
        except Exception as e:
            return False, str(e)

    def test_protected_route_token_mint_post(self):
        """Test POST /api/token-mint requires auth"""
        try:
            response = requests.post(
                f"{BACKEND_URL}/token-mint",
                json={"mint": "So11111111111111111111111111111111111111112", "decimals": 9},
                timeout=10
            )
            status = response.status_code
            
            if status == 401:
                return True, "Correctly returns 401 without auth"
            elif status == 200:
                return False, "CRITICAL: Accepts request without auth (no protection)"
            else:
                return False, f"Unexpected status {status} (expected 401)"
        except Exception as e:
            return False, str(e)

    def test_protected_route_token_mint_delete(self):
        """Test DELETE /api/token-mint requires auth"""
        try:
            response = requests.delete(f"{BACKEND_URL}/token-mint", timeout=10)
            status = response.status_code
            
            if status == 401:
                return True, "Correctly returns 401 without auth"
            elif status == 200:
                return False, "CRITICAL: Accepts request without auth (no protection)"
            else:
                return False, f"Unexpected status {status} (expected 401)"
        except Exception as e:
            return False, str(e)

    def test_protected_route_settings_get(self):
        """Test GET /api/settings requires auth"""
        try:
            response = requests.get(f"{BACKEND_URL}/settings", timeout=10)
            status = response.status_code
            
            if status == 401:
                return True, "Correctly returns 401 without auth"
            elif status == 200:
                return False, "CRITICAL: Accepts request without auth (no protection)"
            else:
                return False, f"Unexpected status {status} (expected 401)"
        except Exception as e:
            return False, str(e)

    def test_protected_route_settings_post(self):
        """Test POST /api/settings requires auth"""
        try:
            response = requests.post(
                f"{BACKEND_URL}/settings",
                json={"autonomy_level": 75},
                timeout=10
            )
            status = response.status_code
            
            if status == 401:
                return True, "Correctly returns 401 without auth"
            elif status == 200:
                return False, "CRITICAL: Accepts request without auth (no protection)"
            else:
                return False, f"Unexpected status {status} (expected 401)"
        except Exception as e:
            return False, str(e)

    def test_protected_route_missions_post(self):
        """Test POST /api/missions requires auth"""
        try:
            response = requests.post(
                f"{BACKEND_URL}/missions",
                json={
                    "name": "Test Mission",
                    "mission_type": "trading",
                    "autonomy": 50,
                    "risk": 30,
                    "reinvest": 60
                },
                timeout=10
            )
            status = response.status_code
            
            if status == 401:
                return True, "Correctly returns 401 without auth"
            elif status == 200:
                return False, "CRITICAL: Accepts request without auth (no protection)"
            else:
                return False, f"Unexpected status {status} (expected 401)"
        except Exception as e:
            return False, str(e)

    def test_protected_route_transactions_post(self):
        """Test POST /api/transactions requires auth"""
        try:
            response = requests.post(
                f"{BACKEND_URL}/transactions",
                json={
                    "type": "sweep",
                    "amount_sol": 1.0,
                    "status": "confirmed"
                },
                timeout=10
            )
            status = response.status_code
            
            if status == 401:
                return True, "Correctly returns 401 without auth"
            elif status == 200:
                return False, "CRITICAL: Accepts request without auth (no protection)"
            else:
                return False, f"Unexpected status {status} (expected 401)"
        except Exception as e:
            return False, str(e)

    def test_protected_route_price_snapshot_post(self):
        """Test POST /api/price-snapshot requires auth"""
        try:
            response = requests.post(
                f"{BACKEND_URL}/price-snapshot",
                json={
                    "mint": "So11111111111111111111111111111111111111112",
                    "price": 100.0
                },
                timeout=10
            )
            status = response.status_code
            
            if status == 401:
                return True, "Correctly returns 401 without auth"
            elif status == 200:
                return False, "CRITICAL: Accepts request without auth (no protection)"
            else:
                return False, f"Unexpected status {status} (expected 401)"
        except Exception as e:
            return False, str(e)

    def test_protected_route_treasury_snapshot_post(self):
        """Test POST /api/treasury-snapshot requires auth"""
        try:
            response = requests.post(
                f"{BACKEND_URL}/treasury-snapshot",
                json={
                    "address": "HTN1fvHwbzKiMwh9YXZEe3eooiMdoCAs3TweWdiSZV5i",
                    "balance_sol": 10.0
                },
                timeout=10
            )
            status = response.status_code
            
            if status == 401:
                return True, "Correctly returns 401 without auth"
            elif status == 200:
                return False, "CRITICAL: Accepts request without auth (no protection)"
            else:
                return False, f"Unexpected status {status} (expected 401)"
        except Exception as e:
            return False, str(e)

    def test_protected_route_events_post(self):
        """Test POST /api/events requires auth"""
        try:
            response = requests.post(
                f"{BACKEND_URL}/events",
                json={
                    "text": "Test event",
                    "category": "system"
                },
                timeout=10
            )
            status = response.status_code
            
            if status == 401:
                return True, "Correctly returns 401 without auth"
            elif status == 200:
                return False, "CRITICAL: Accepts request without auth (no protection)"
            else:
                return False, f"Unexpected status {status} (expected 401)"
        except Exception as e:
            return False, str(e)

    def test_protected_route_sweep_post(self):
        """Test POST /api/sweep requires auth"""
        try:
            response = requests.post(
                f"{BACKEND_URL}/sweep",
                json={
                    "from": "HTN1fvHwbzKiMwh9YXZEe3eooiMdoCAs3TweWdiSZV5i",
                    "to": "7ApE9ABS11vdQCSPiPikGHcMU2iF7sFqRdSQUX1cwD7Z",
                    "amount_sol": 1.0,
                    "signature": "test"
                },
                timeout=10
            )
            status = response.status_code
            
            if status == 401:
                return True, "Correctly returns 401 without auth"
            elif status == 200:
                return False, "CRITICAL: Accepts request without auth (no protection)"
            else:
                return False, f"Unexpected status {status} (expected 401)"
        except Exception as e:
            return False, str(e)

    def test_protected_route_revenue_dashboard(self):
        """Test GET /api/revenue/dashboard requires auth"""
        try:
            response = requests.get(f"{BACKEND_URL}/revenue/dashboard", timeout=10)
            status = response.status_code
            
            if status == 401:
                return True, "Correctly returns 401 without auth"
            elif status == 200:
                return False, "CRITICAL: Accepts request without auth (no protection)"
            else:
                return False, f"Unexpected status {status} (expected 401)"
        except Exception as e:
            return False, str(e)

    def test_protected_route_compliance_check(self):
        """Test POST /api/revenue/compliance/check requires auth"""
        try:
            response = requests.post(
                f"{BACKEND_URL}/revenue/compliance/check",
                json={
                    "text": "Test compliance check",
                    "context": "general"
                },
                timeout=10
            )
            status = response.status_code
            
            if status == 401:
                return True, "Correctly returns 401 without auth"
            elif status == 200:
                return False, "CRITICAL: Accepts request without auth (no protection)"
            else:
                return False, f"Unexpected status {status} (expected 401)"
        except Exception as e:
            return False, str(e)

    def test_public_route_root(self):
        """Test GET /api/ is public (no auth required)"""
        try:
            response = requests.get(f"{BACKEND_URL}/", timeout=10)
            status = response.status_code
            
            if status == 200:
                data = response.json()
                if data.get("status") == "ok":
                    return True, "Public route works without auth"
                else:
                    return False, "Unexpected response format"
            else:
                return False, f"Unexpected status {status} (expected 200)"
        except Exception as e:
            return False, str(e)

    def test_public_route_analytics(self):
        """Test GET /api/analytics is public (no auth required)"""
        try:
            response = requests.get(f"{BACKEND_URL}/analytics", timeout=10)
            status = response.status_code
            
            if status == 200:
                return True, "Public route works without auth"
            elif status == 401:
                return False, "Analytics endpoint requires auth (should be public)"
            else:
                return False, f"Unexpected status {status} (expected 200)"
        except Exception as e:
            return False, str(e)

    def test_public_route_revenue_status(self):
        """Test GET /api/revenue/status is public (no auth required)"""
        try:
            response = requests.get(f"{BACKEND_URL}/revenue/status", timeout=10)
            status = response.status_code
            
            if status == 200:
                return True, "Public route works without auth"
            elif status == 401:
                return False, "Revenue status endpoint requires auth (should be public)"
            else:
                return False, f"Unexpected status {status} (expected 200)"
        except Exception as e:
            return False, str(e)

def main():
    print("=" * 70)
    print("YABBAI HUB SSO AUTHENTICATION TEST")
    print("=" * 70)
    print(f"Backend URL: {BACKEND_URL}")
    print(f"Testing Hub SSO integration (zero-credential spoke)")
    print("=" * 70)
    
    tester = HubSSOTester()
    
    # Test 1: Core SSO functionality
    print("\n" + "=" * 70)
    print("CORE SSO FUNCTIONALITY")
    print("=" * 70)
    tester.run_test("Auth Check - /api/auth/me returns 401", tester.test_auth_me_returns_401)
    
    # Test 2: Protected write routes
    print("\n" + "=" * 70)
    print("PROTECTED WRITE ROUTES (require Director auth)")
    print("=" * 70)
    tester.run_test("POST /api/token-mint", tester.test_protected_route_token_mint_post)
    tester.run_test("DELETE /api/token-mint", tester.test_protected_route_token_mint_delete)
    tester.run_test("GET /api/settings", tester.test_protected_route_settings_get)
    tester.run_test("POST /api/settings", tester.test_protected_route_settings_post)
    tester.run_test("POST /api/missions", tester.test_protected_route_missions_post)
    tester.run_test("POST /api/transactions", tester.test_protected_route_transactions_post)
    tester.run_test("POST /api/price-snapshot", tester.test_protected_route_price_snapshot_post)
    tester.run_test("POST /api/treasury-snapshot", tester.test_protected_route_treasury_snapshot_post)
    tester.run_test("POST /api/events", tester.test_protected_route_events_post)
    tester.run_test("POST /api/sweep", tester.test_protected_route_sweep_post)
    tester.run_test("GET /api/revenue/dashboard", tester.test_protected_route_revenue_dashboard)
    tester.run_test("POST /api/revenue/compliance/check", tester.test_protected_route_compliance_check)
    
    # Test 3: Public routes
    print("\n" + "=" * 70)
    print("PUBLIC ROUTES (no auth required)")
    print("=" * 70)
    tester.run_test("GET /api/", tester.test_public_route_root)
    tester.run_test("GET /api/analytics", tester.test_public_route_analytics)
    tester.run_test("GET /api/revenue/status", tester.test_public_route_revenue_status)
    
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
        print("\n✅ ALL TESTS PASSED - Hub SSO authentication is working correctly!")
        return 0
    else:
        print(f"\n❌ {tester.tests_run - tester.tests_passed} TESTS FAILED - Issues need to be fixed")
        return 1

if __name__ == "__main__":
    sys.exit(main())
