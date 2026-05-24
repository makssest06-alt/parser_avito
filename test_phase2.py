import time
from database import Database
from parser_service import ParserService

def test():
    db = Database()
    
    # Insert test user and subscription and link
    user_id = 999999
    
    import sqlite3
    with sqlite3.connect('users.db') as conn:
        cursor = conn.cursor()
        cursor.execute("INSERT OR REPLACE INTO users (user_id, username, is_active) VALUES (?, 'testuser', 1)", (user_id,))
        cursor.execute("INSERT OR REPLACE INTO subscriptions (user_id, subscription_type, start_date, end_date, is_active) VALUES (?, 'Premium', datetime('now'), datetime('now', '+1 month'), 1)", (user_id,))
        cursor.execute("INSERT OR REPLACE INTO user_links (user_id, avito_link, is_active) VALUES (?, 'https://www.avito.ru/moskva/telefony/apple-ASgBAgICAUTkAwQ', 1)", (user_id,))
        cursor.execute("INSERT OR REPLACE INTO parser_settings (user_id, tg_notifications) VALUES (?, 0)", (user_id,)) # disable TG for test
        conn.commit()
        
    print("Test data inserted. Links with users:")
    print(db.get_all_active_links_with_users())

    service = ParserService()
    service.is_running = True # Bypass start_monitoring
    
    # Run one pass of the loop manually
    try:
        links_with_users = service.db.get_all_active_links_with_users()
        if not links_with_users:
            print("No links found!")
            return
            
        print(f"Found links: {links_with_users}")
        
        generic_config = service._create_config([], service._get_default_settings(), 0)
        from parser_cls import AvitoParse
        parser = AvitoParse(generic_config, stop_event=service.stop_event)
        
        for url, user_ids in links_with_users.items():
            print(f"Parsing url {url} for users {user_ids}")
            ads = parser.get_ads_from_url(url)
            print(f"Fetched {len(ads)} ads")
            
            for uid in user_ids:
                settings = service.db.get_parser_settings(uid) or service._get_default_settings()
                user_config = service._create_config([url], settings, uid)
                from parser.filters import AdsFilter
                filtered_ads = AdsFilter.filter_ads(ads, user_config)
                print(f"User {uid} filtered down to {len(filtered_ads)} ads")
                
        print("Test complete!")
        
    except Exception as e:
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    test()