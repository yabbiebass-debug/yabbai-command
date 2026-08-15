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

    # ── Phase 3+4 Tests ──────────────────────────────────────────────────────

    def test_get_settings(self):
        """Test getting settings (should return defaults if empty)"""
        return self.run_test(
            "Get Settings",
            "GET",
            "settings",
            200
        )

    def test_save_settings(self):
        """Test saving settings"""
        return self.run_test(
            "Save Settings",
            "POST",
            "settings",
            200,
            data={
                "treasury_wallet": "7dzgCA8G55VytZ8PS1b99rbbctzCgJbnEoBEYBnn15YR",
                "main_wallet": "TestWallet123456789012345678901234567890",
                "slippage_bps": 100,
                "autonomy_level": 80,
                "risk_appetite": 50,
                "demo_mode": True
            }
        )

    def test_create_mission(self):
        """Test creating a mission"""
        success, response = self.run_test(
            "Create Mission",
            "POST",
            "missions",
            200,
            data={
                "name": "Test Mission Alpha",
                "mission_type": "yield_farming",
                "autonomy": 75,
                "risk": 40,
                "reinvest": 60,
                "self_improve": True,
                "status": "active",
                "estimated_apy": 120
            }
        )
        if success and response.get('id'):
            self.mission_id = response['id']
            print(f"   ✓ Mission created with ID: {self.mission_id}")
        return success, response

    def test_list_missions(self):
        """Test listing missions"""
        success, response = self.run_test(
            "List Missions",
            "GET",
            "missions",
            200
        )
        if success:
            print(f"   ✓ Found {len(response)} mission(s)")
        return success, response

    def test_record_transaction(self):
        """Test recording a transaction"""
        success, response = self.run_test(
            "Record Transaction",
            "POST",
            "transactions",
            200,
            data={
                "type": "sweep",
                "amount_sol": 1.234,
                "from_address": "7dzgCA8G55VytZ8PS1b99rbbctzCgJbnEoBEYBnn15YR",
                "to_address": "TestWallet123456789012345678901234567890",
                "status": "confirmed",
                "label": "Test sweep"
            }
        )
        if success and response.get('id'):
            print(f"   ✓ Transaction recorded with ID: {response['id']}")
        return success, response

    def test_list_transactions(self):
        """Test listing transactions"""
        success, response = self.run_test(
            "List Transactions",
            "GET",
            "transactions",
            200,
            params={"limit": 50}
        )
        if success:
            print(f"   ✓ Found {len(response)} transaction(s)")
        return success, response

    def test_add_price_snapshot(self):
        """Test adding a price snapshot"""
        return self.run_test(
            "Add Price Snapshot",
            "POST",
            "price-snapshot",
            200,
            data={
                "mint": "So11111111111111111111111111111111111111112",
                "price": 0.002441
            }
        )

    def test_get_price_history(self):
        """Test getting price history"""
        success, response = self.run_test(
            "Get Price History",
            "GET",
            "price-history",
            200,
            params={"mint": "So11111111111111111111111111111111111111112", "limit": 100}
        )
        if success and response.get('ok'):
            print(f"   ✓ Found {len(response.get('points', []))} price point(s)")
        return success, response

    def test_add_treasury_snapshot(self):
        """Test adding a treasury snapshot"""
        return self.run_test(
            "Add Treasury Snapshot",
            "POST",
            "treasury-snapshot",
            200,
            data={
                "address": "7dzgCA8G55VytZ8PS1b99rbbctzCgJbnEoBEYBnn15YR",
                "balance_sol": 124.7,
                "balance_usd": 22234.74
            }
        )

    def test_get_treasury_snapshots(self):
        """Test getting treasury snapshots"""
        success, response = self.run_test(
            "Get Treasury Snapshots",
            "GET",
            "treasury-snapshots",
            200,
            params={"limit": 100}
        )
        if success:
            print(f"   ✓ Found {len(response)} treasury snapshot(s)")
        return success, response

    def test_add_event(self):
        """Test adding an event"""
        return self.run_test(
            "Add Event",
            "POST",
            "events",
            200,
            data={
                "text": "Test event from backend_test.py",
                "color": "event-green",
                "category": "test"
            }
        )

    def test_get_events(self):
        """Test getting events"""
        success, response = self.run_test(
            "Get Events",
            "GET",
            "events",
            200,
            params={"limit": 40}
        )
        if success:
            print(f"   ✓ Found {len(response)} event(s)")
        return success, response

    def test_get_analytics(self):
        """Test getting analytics aggregate"""
        success, response = self.run_test(
            "Get Analytics",
            "GET",
            "analytics",
            200
        )
        if success:
            print(f"   ✓ Analytics: {response.get('tx_count', 0)} txs, {response.get('mission_count', 0)} missions")
            print(f"   ✓ Total swept: {response.get('total_swept_sol', 0)} SOL")
        return success, response

    # ── Truth Protocol / Data Integrity Tests ────────────────────────────────

    def test_revenue_status(self):
        """Test revenue system status - should show real data only"""
        success, response = self.run_test(
            "Revenue Status (Truth Protocol)",
            "GET",
            "revenue/status",
            200
        )
        if success:
            real_income = response.get('real_income', 0)
            net_profit = response.get('net_profit', 0)
            print(f"   ✓ Real Income: ${real_income:.2f}")
            print(f"   ✓ Net Profit: ${net_profit:.2f}")
            # Verify it's showing $0.00 with no payment processor data
            if real_income == 0:
                print(f"   ✓ Correctly showing $0.00 (no payment processor data)")
        return success, response

    def test_agents_status(self):
        """Test agent pool status - should show real agent data"""
        success, response = self.run_test(
            "Agent Pool Status",
            "GET",
            "agents/status",
            200
        )
        if success:
            total_agents = response.get('total_agents', 0)
            total_cycles = response.get('total_cycles', 0)
            print(f"   ✓ Total Agents: {total_agents}")
            print(f"   ✓ Total Cycles: {total_cycles}")
        return success, response

    def test_health_details(self):
        """Test health details endpoint - should return real service metrics"""
        success, response = self.run_test(
            "Health Details (Real Metrics)",
            "GET",
            "health/details",
            200
        )
        if success:
            services = response.get('services', [])
            print(f"   ✓ Monitoring {len(services)} service(s)")
            for service in services:
                status = service.get('status', 'unknown')
                latency = service.get('latency', 0)
                name = service.get('name', 'Unknown')
                print(f"   ✓ {name}: {status} ({latency}ms)")
        return success, response

    def test_live_income_stream(self):
        """Test live income stream - should only show payment processor data"""
        success, response = self.run_test(
            "Live Income Stream (Payment Processor Only)",
            "GET",
            "revenue/live/income",
            200,
            params={"limit": 100}
        )
        if success:
            income_items = response.get('income', [])
            total = response.get('total', 0)
            print(f"   ✓ Income entries: {len(income_items)}")
            print(f"   ✓ Total: ${total:.2f}")
            
            # Verify all entries are from payment processor
            non_payment_sources = [item for item in income_items if item.get('source') not in ['product_sale', 'invoice_paid']]
            if non_payment_sources:
                print(f"   ⚠ WARNING: Found {len(non_payment_sources)} non-payment-processor entries")
            else:
                print(f"   ✓ All entries are from payment processor sources")
        return success, response

    # ── Code Quality Improvements Tests ──────────────────────────────────────

    def test_health_details_performance(self):
        """Test health details endpoint performance - should complete in <5s with concurrent checks"""
        import time
        print(f"\n🔍 Testing Health Details Performance (Concurrent Execution)...")
        
        url = f"{self.api_url}/health/details"
        headers = {'Content-Type': 'application/json'}
        
        self.tests_run += 1
        
        try:
            start_time = time.time()
            response = requests.get(url, headers=headers, timeout=10)
            elapsed_time = time.time() - start_time
            
            success = response.status_code == 200 and elapsed_time < 5.0
            
            if response.status_code == 200:
                data = response.json()
                services = data.get('services', [])
                
                print(f"✅ Status: {response.status_code}")
                print(f"   ✓ Response time: {elapsed_time:.2f}s (target: <5s)")
                print(f"   ✓ Services checked: {len(services)}")
                
                # Verify all expected services are present
                expected_services = ['mongodb', 'sol-rpc', 'jup', 'revenue', 'agents']
                found_services = [s.get('id') for s in services]
                
                for expected in expected_services:
                    if expected in found_services:
                        service = next(s for s in services if s.get('id') == expected)
                        print(f"   ✓ {service.get('name')}: {service.get('status')} ({service.get('latency')}ms)")
                    else:
                        print(f"   ⚠ Missing service: {expected}")
                        success = False
                
                if elapsed_time < 5.0:
                    print(f"   ✅ PASS: Concurrent execution working (completed in {elapsed_time:.2f}s)")
                    self.tests_passed += 1
                else:
                    print(f"   ❌ FAIL: Too slow ({elapsed_time:.2f}s), concurrent execution may not be working")
                
                self.test_results.append({
                    "test": "Health Details Performance",
                    "status": "PASS" if success else "FAIL",
                    "response_time": f"{elapsed_time:.2f}s",
                    "services_count": len(services)
                })
                
                return success, data
            else:
                print(f"❌ Failed - Status: {response.status_code}")
                self.test_results.append({"test": "Health Details Performance", "status": "FAIL", "error": f"Status {response.status_code}"})
                return False, {}
                
        except Exception as e:
            print(f"❌ Failed - Error: {str(e)}")
            self.test_results.append({"test": "Health Details Performance", "status": "FAIL", "error": str(e)})
            return False, {}

    def test_withdrawal_whitelist_validation(self):
        """Test withdrawal whitelist - should reject unauthorized addresses"""
        print(f"\n🔍 Testing Withdrawal Whitelist Security...")
        
        self.tests_run += 1
        
        # Test 1: Validate authorized address
        authorized_address = "7ApE9ABS11vdQCSPiPikGHcMU2iF7sFqRdSQUX1cwD7Z"
        success1, response1 = self.run_test(
            "Validate Authorized Address",
            "GET",
            "sweep/validate-destination",
            200,
            params={"address": authorized_address}
        )
        
        if success1:
            if response1.get('authorized'):
                print(f"   ✅ Authorized address correctly validated")
            else:
                print(f"   ❌ Authorized address incorrectly rejected")
                return False, response1
        
        # Test 2: Validate unauthorized address
        unauthorized_address = "UnauthorizedWallet1111111111111111111111111"
        success2, response2 = self.run_test(
            "Validate Unauthorized Address",
            "GET",
            "sweep/validate-destination",
            200,
            params={"address": unauthorized_address}
        )
        
        if success2:
            if not response2.get('authorized'):
                print(f"   ✅ Unauthorized address correctly rejected")
            else:
                print(f"   ❌ Unauthorized address incorrectly allowed")
                return False, response2
        
        # Test 3: Attempt sweep to unauthorized address (should fail with 403)
        print(f"\n🔍 Testing Sweep to Unauthorized Address (should fail)...")
        success3, response3 = self.run_test(
            "Sweep to Unauthorized Address",
            "POST",
            "sweep",
            403,  # Should return 403 Forbidden
            data={
                "from": "7dzgCA8G55VytZ8PS1b99rbbctzCgJbnEoBEYBnn15YR",
                "to": unauthorized_address,
                "amount_sol": 1.0,
                "signature": "test_signature_123"
            }
        )
        
        if success3:
            print(f"   ✅ Sweep to unauthorized address correctly blocked")
            self.tests_passed += 1
        else:
            print(f"   ❌ Sweep to unauthorized address was not blocked properly")
        
        self.test_results.append({
            "test": "Withdrawal Whitelist Security",
            "status": "PASS" if (success1 and success2 and success3) else "FAIL"
        })
        
        return success1 and success2 and success3, {}

def main():
    print("=" * 60)
    print("YABBAI BACKEND API TEST SUITE - PHASE 3+4")
    print("=" * 60)
    print(f"Started at: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print()

    tester = YabbaiAPITester()
    tester.mission_id = None

    # Run all tests
    print("\n" + "=" * 60)
    print("PHASE 1+2 TESTS (BASELINE)")
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

    print("\n" + "=" * 60)
    print("PHASE 3+4 TESTS (NEW ENDPOINTS)")
    print("=" * 60)

    # Settings
    tester.test_get_settings()
    tester.test_save_settings()

    # Missions
    tester.test_create_mission()
    tester.test_list_missions()

    # Transactions
    tester.test_record_transaction()
    tester.test_list_transactions()

    # Price history
    tester.test_add_price_snapshot()
    tester.test_get_price_history()

    # Treasury snapshots
    tester.test_add_treasury_snapshot()
    tester.test_get_treasury_snapshots()

    # Events
    tester.test_add_event()
    tester.test_get_events()

    # Analytics aggregate
    tester.test_get_analytics()

    print("\n" + "=" * 60)
    print("TRUTH PROTOCOL / DATA INTEGRITY TESTS")
    print("=" * 60)

    # Revenue system (Truth Protocol)
    tester.test_revenue_status()
    
    # Agent pool status
    tester.test_agents_status()
    
    # Health details (real service metrics)
    tester.test_health_details()
    
    # Live income stream (payment processor only)
    tester.test_live_income_stream()

    print("\n" + "=" * 60)
    print("CODE QUALITY IMPROVEMENTS TESTS")
    print("=" * 60)

    # Test concurrent health checks performance
    tester.test_health_details_performance()
    
    # Test withdrawal whitelist security
    tester.test_withdrawal_whitelist_validation()

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
