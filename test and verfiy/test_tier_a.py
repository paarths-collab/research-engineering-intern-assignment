from scraper_tier_a import TIER_A_DOMAINS, scrape_tier_a

def test_all_domains():
    print(f"Testing {len(TIER_A_DOMAINS)} domains...")
    success_count = 0
    fail_count = 0
    
    for domain in sorted(TIER_A_DOMAINS):
        url = f"https://{domain}"
        print(f"Testing {url}...", end=" ", flush=True)
        res = scrape_tier_a(url, retries=0)
        
        # Note: testing root domain might not return article text, but we can check if it 
        # at least fetches the HTML without getting blocked.
        if res.error and "fetch_url returned empty" in res.error:
            print("❌ BLOCKED / ERROR")
            fail_count += 1
        elif res.success or res.error == "trafilatura.extract returned None — boilerplate-only page?" or "Extraction produced empty text body" in (res.error or ""):
            print("✅ OK")
            success_count += 1
        else:
            print(f"⚠️ {res.error}")
            fail_count += 1
            
    print(f"\nResults: {success_count} OK, {fail_count} Failed.")

if __name__ == "__main__":
    test_all_domains()
