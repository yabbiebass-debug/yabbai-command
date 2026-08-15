#!/usr/bin/env python3
"""
Fix database to use NEW treasury wallet and remove old wallet data
"""
import asyncio
from motor.motor_asyncio import AsyncIOMotorClient
import os
from datetime import datetime, timezone

# Database connection
MONGO_URL = "mongodb://localhost:27017"
DB_NAME = "test_database"

# Wallet addresses
NEW_TREASURY_WALLET = "HTN1fvHwbzKiMwh9YXZEe3eooiMdoCAs3TweWdiSZV5i"
OLD_TREASURY_WALLET = "7dzgCA8G55VytZ8PS1b99rbbctzCgJbnEoBEYBnn15YR"

async def fix_database():
    """Fix database to use NEW treasury wallet"""
    client = AsyncIOMotorClient(MONGO_URL)
    db = client[DB_NAME]
    
    print("=" * 70)
    print("DATABASE FIX - Update Treasury Wallet Configuration")
    print("=" * 70)
    print(f"OLD Treasury Wallet: {OLD_TREASURY_WALLET}")
    print(f"NEW Treasury Wallet: {NEW_TREASURY_WALLET}")
    print("=" * 70)
    
    # 1. Update settings collection
    print("\n1️⃣  Updating settings collection...")
    settings = await db.settings.find_one({})
    if settings:
        old_treasury = settings.get("treasury_wallet", "")
        print(f"   Current treasury wallet: {old_treasury}")
        
        if old_treasury == OLD_TREASURY_WALLET:
            result = await db.settings.update_one(
                {},
                {
                    "$set": {
                        "treasury_wallet": NEW_TREASURY_WALLET,
                        "updated_at": datetime.now(timezone.utc).isoformat()
                    }
                }
            )
            print(f"   ✅ Updated settings to NEW treasury wallet")
            print(f"   Modified count: {result.modified_count}")
        elif old_treasury == NEW_TREASURY_WALLET:
            print(f"   ✅ Settings already using NEW treasury wallet")
        else:
            print(f"   ⚠️  Unknown treasury wallet: {old_treasury}")
    else:
        # Create settings with NEW treasury wallet
        await db.settings.insert_one({
            "treasury_wallet": NEW_TREASURY_WALLET,
            "main_wallet": "",
            "updated_at": datetime.now(timezone.utc).isoformat()
        })
        print(f"   ✅ Created settings with NEW treasury wallet")
    
    # 2. Delete old treasury snapshots
    print("\n2️⃣  Deleting old treasury snapshots...")
    old_snapshots = await db.treasury_snapshots.find(
        {"address": OLD_TREASURY_WALLET}
    ).to_list(None)
    
    print(f"   Found {len(old_snapshots)} old wallet snapshots")
    
    if old_snapshots:
        # Show details of snapshots being deleted
        for snap in old_snapshots:
            balance = snap.get("balance_sol", 0)
            ts = snap.get("ts", "")
            print(f"   - Deleting snapshot: {balance} SOL at {ts}")
        
        result = await db.treasury_snapshots.delete_many(
            {"address": OLD_TREASURY_WALLET}
        )
        print(f"   ✅ Deleted {result.deleted_count} old wallet snapshots")
    else:
        print(f"   ✅ No old wallet snapshots found")
    
    # 3. Check for transactions referencing old wallet
    print("\n3️⃣  Checking transactions for old wallet references...")
    old_tx_from = await db.transactions.count_documents(
        {"from_address": OLD_TREASURY_WALLET}
    )
    old_tx_to = await db.transactions.count_documents(
        {"to_address": OLD_TREASURY_WALLET}
    )
    
    print(f"   Transactions FROM old wallet: {old_tx_from}")
    print(f"   Transactions TO old wallet: {old_tx_to}")
    
    if old_tx_from > 0 or old_tx_to > 0:
        print(f"   ⚠️  Found {old_tx_from + old_tx_to} transactions referencing old wallet")
        print(f"   Note: Keeping transactions for historical record")
    else:
        print(f"   ✅ No transactions reference old wallet")
    
    # 4. Verify token_mint_config
    print("\n4️⃣  Checking token_mint_config...")
    mint_config = await db.token_mint_config.find_one({})
    if mint_config:
        treasury = mint_config.get("treasury", "")
        if treasury == OLD_TREASURY_WALLET:
            result = await db.token_mint_config.update_one(
                {},
                {"$set": {"treasury": NEW_TREASURY_WALLET}}
            )
            print(f"   ✅ Updated token_mint_config treasury to NEW wallet")
        elif treasury == NEW_TREASURY_WALLET:
            print(f"   ✅ token_mint_config already using NEW treasury wallet")
        else:
            print(f"   ℹ️  token_mint_config treasury: {treasury}")
    else:
        print(f"   ℹ️  No token_mint_config found")
    
    # 5. Summary
    print("\n" + "=" * 70)
    print("DATABASE FIX SUMMARY")
    print("=" * 70)
    
    # Verify settings
    settings = await db.settings.find_one({})
    current_treasury = settings.get("treasury_wallet", "") if settings else ""
    
    # Count snapshots
    new_snapshots = await db.treasury_snapshots.count_documents(
        {"address": NEW_TREASURY_WALLET}
    )
    old_snapshots_remaining = await db.treasury_snapshots.count_documents(
        {"address": OLD_TREASURY_WALLET}
    )
    
    print(f"✅ Settings treasury wallet: {current_treasury}")
    print(f"✅ NEW wallet snapshots: {new_snapshots}")
    print(f"✅ OLD wallet snapshots remaining: {old_snapshots_remaining}")
    
    if current_treasury == NEW_TREASURY_WALLET and old_snapshots_remaining == 0:
        print("\n🎉 DATABASE FIX COMPLETE - All issues resolved!")
    else:
        print("\n⚠️  Some issues may remain - please verify")
    
    client.close()

if __name__ == "__main__":
    asyncio.run(fix_database())
