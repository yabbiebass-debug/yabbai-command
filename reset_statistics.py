#!/usr/bin/env python3
"""
Reset statistics for new token launch
Clears: transactions, treasury snapshots, price history, events, token mint config
Preserves: settings, missions, revenue system
"""
import os
import asyncio
from motor.motor_asyncio import AsyncIOMotorClient
from dotenv import load_dotenv
from pathlib import Path

ROOT_DIR = Path(__file__).parent / 'backend'
load_dotenv(ROOT_DIR / '.env')

async def reset_statistics():
    """Reset all statistics while preserving settings and missions."""
    
    mongo_url = os.environ['MONGO_URL']
    client = AsyncIOMotorClient(mongo_url)
    db = client[os.environ.get('DB_NAME', 'yabbai')]
    
    print("🔄 Starting statistics reset...")
    print("=" * 60)
    
    # Collections to reset
    collections_to_clear = [
        ('transactions', 'Transaction history'),
        ('treasury_snapshots', 'Treasury balance snapshots'),
        ('price_history', 'Price history data'),
        ('events', 'Analytics events log'),
        ('token_mint_config', 'Token mint configuration'),
    ]
    
    results = []
    
    for collection_name, description in collections_to_clear:
        try:
            count_before = await db[collection_name].count_documents({})
            result = await db[collection_name].delete_many({})
            results.append({
                'collection': collection_name,
                'description': description,
                'deleted': result.deleted_count,
                'before': count_before
            })
            print(f"✅ {description}: Deleted {result.deleted_count} records")
        except Exception as e:
            print(f"❌ Error clearing {collection_name}: {e}")
            results.append({
                'collection': collection_name,
                'description': description,
                'error': str(e)
            })
    
    print("=" * 60)
    print("\n📊 Verification:")
    
    # Verify preserved collections
    preserved_collections = [
        ('settings', 'Settings'),
        ('missions', 'Missions'),
    ]
    
    for collection_name, description in preserved_collections:
        try:
            count = await db[collection_name].count_documents({})
            print(f"✅ {description}: {count} records preserved")
        except Exception as e:
            print(f"⚠️  {description}: {e}")
    
    print("\n" + "=" * 60)
    print("🎉 Statistics reset complete!")
    print("✨ System ready for new token mint")
    
    client.close()
    return results

if __name__ == "__main__":
    asyncio.run(reset_statistics())
