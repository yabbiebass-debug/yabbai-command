import requests
import sys
from datetime import datetime

class YabbaiAPITester:
    def __init__(self, base_url="https://yabbai-command.preview.emergentagent.com"):
        self.base_url = base_url
        self.api_url = f"{base_url}/api"
        self.tests_run = 0
        self.tests_passed = 0
        self.test_results = []

    def run_test(self, name, method, endpoint, expected_status, data=None, params=None):
        """Run a single API test"""
        url = f"{self.api_url}/{endpoint}" if endpoint else self.api_url
        headers = {'Content-Type': 'application/json'}

        self.tests_run += 1
        print(f"\n🔍 Testing {name}...")
        
        try:
            if method == 'GET':
                response = requests.get(url, headers=headers, params=params, timeout=10)
            elif method == 'POST':
                response = requests.post(url, json=data, headers=headers, timeout=10)
            elif method == 'DELETE':
                response = requests.delete(url, headers=headers, timeout=10)

            success = response.status_code == expected_status
            result = {
                "test": name,
                "status": "PASS" if success else "FAIL",
                "expected": expected_status,
                "actual": response.status_code,
                "response": response.json() if response.headers.get('content-type', '').startswith('application/json') else response.text[:200]
            }
            
            if success:
                self.tests_passed += 1
                print(f"✅ Passed - Status: {response.status_code}")
                if response.headers.get('content-type', '').startswith('application/json'):
                    print(f"   Response: {response.json()}")
            else:
                print(f"❌ Failed - Expected {expected_status}, got {response.status_code}")
                print(f"   Response: {result['response']}")

            self.test_results.append(result)
            return success, response.json() if response.headers.get('content-type', '').startswith('application/json') else {}

        except requests.exceptions.Timeout:
            print(f"❌ Failed - Request timeout")
            self.test_results.append({"test": name, "status": "FAIL", "error": "Timeout"})
            return False, {}
        except Exception as e:
            print(f"❌ Failed - Error: {str(e)}")
            self.test_results.append({"test": name, "status": "FAIL", "error": str(e)})
            return False, {}

    def test_health_check(self):
        """Test API health check"""
        return self.run_test(
            "API Health Check",
            "GET",
            "",
            200
        )

    def test_get_token_mint_empty(self):
        """Test getting token mint config when empty"""
        return self.run_test(
            "Get Token Mint (Empty)",
            "GET",
            "token-mint",
            200
        )

    def test_save_token_mint(self):
        """Test saving token mint configuration"""
        # Using a valid Solana address format (SOL mint as example)
        test_mint = "So11111111111111111111111111111111111111112"
        return self.run_test(
            "Save Token Mint",
            "POST",
            "token-mint",
            200,
            data={
                "mint": test_mint,
                "decimals": 6,
                "supply": "1000000000",
                "treasury": "7dzgCA8G55VytZ8PS1b99rbbctzCgJbnEoBEYBnn15YR",
                "network": "mainnet-beta",
                "launchpad": "pump"
            }
        )

    def test_get_token_mint_configured(self):
        """Test getting token mint config after saving"""
        success, response = self.run_test(
            "Get Token Mint (Configured)",
            "GET",
            "token-mint",
            200
        )
        if success and response.get('configured'):
            print(f"   ✓ Token mint configured: {response.get('mint', 'N/A')}")
        return success, response

    def test_jupiter_price(self):
        """Test Jupiter price API proxy"""
        # Using SOL mint address
        sol_mint = "So11111111111111111111111111111111111111112"
        success, response = self.run_test(
            "Jupiter Price API",
            "GET",
            "jupiter-price",
            200,
            params={"mint": sol_mint}
        )
        if success:
            if response.get('ok'):
                print(f"   ✓ Price fetched: ${response.get('price', 'N/A')}")
            else:
                print(f"   ⚠ API returned ok=False: {response.get('error', 'Unknown error')}")
        return success, response

    def test_solana_balance(self):
        """Test Solana balance API proxy"""
        # Using YABBAI treasury address
        treasury = "7dzgCA8G55VytZ8PS1b99rbbctzCgJbnEoBEYBnn15YR"
        success, response = self.run_test(
            "Solana Balance API",
            "GET",
            "solana-balance",
            200,
            params={"owner": treasury}
        )
        if success:
            if response.get('ok'):
                print(f"   ✓ SOL Balance: {response.get('sol', 0)} SOL")
                print(f"   ✓ Token accounts: {len(response.get('tokens', []))}")
            else:
                print(f"   ⚠ API returned ok=False: {response.get('error', 'Unknown error')}")
        return success, response

    def test_delete_token_mint(self):
        """Test deleting token mint configuration"""
        return self.run_test(
            "Delete Token Mint",
            "DELETE",
            "token-mint",
            200
        )

    def test_invalid_mint_address(self):
        """Test saving with invalid mint address"""
        return self.run_test(
            "Invalid Mint Address",
            "POST",
            "token-mint",
            400,
            data={
                "mint": "invalid",
                "decimals": 6
            }
        )

def main():
    print("=" * 60)
    print("YABBAI BACKEND API TEST SUITE")
    print("=" * 60)
    print(f"Started at: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print()

    tester = YabbaiAPITester()

    # Run all tests
    print("\n" + "=" * 60)
    print("RUNNING TESTS")
    print("=" * 60)

    # 1. Health check
    tester.test_health_check()

    # 2. Token mint CRUD
    tester.test_get_token_mint_empty()
    tester.test_save_token_mint()
    tester.test_get_token_mint_configured()
    
    # 3. External API proxies
    tester.test_jupiter_price()
    tester.test_solana_balance()
    
    # 4. Validation
    tester.test_invalid_mint_address()
    
    # 5. Cleanup
    tester.test_delete_token_mint()

    # Print summary
    print("\n" + "=" * 60)
    print("TEST SUMMARY")
    print("=" * 60)
    print(f"Total tests: {tester.tests_run}")
    print(f"Passed: {tester.tests_passed}")
    print(f"Failed: {tester.tests_run - tester.tests_passed}")
    print(f"Success rate: {(tester.tests_passed / tester.tests_run * 100):.1f}%")
    
    # Print failed tests
    failed_tests = [r for r in tester.test_results if r['status'] == 'FAIL']
    if failed_tests:
        print("\n❌ FAILED TESTS:")
        for test in failed_tests:
            print(f"  - {test['test']}")
            if 'error' in test:
                print(f"    Error: {test['error']}")
            else:
                print(f"    Expected: {test.get('expected')}, Got: {test.get('actual')}")
    
    print("\n" + "=" * 60)
    print(f"Completed at: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 60)

    return 0 if tester.tests_passed == tester.tests_run else 1

if __name__ == "__main__":
    sys.exit(main())
