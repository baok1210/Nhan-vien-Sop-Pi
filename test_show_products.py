import json

with open('data/example/products.json', encoding='utf-8') as f:
    products = json.load(f)

print(f'Total: {len(products)} san pham\n')
for i, p in enumerate(products, 1):
    title = p.get('title_cn', p.get('title_en', ''))[:80]
    price = p.get('price_cny', 0)
    vnd = int(price * 3500)
    supplier = p.get('supplier_name', 'N/A')
    rating = p.get('supplier_rating', 'N/A')
    url = p.get('detail_url', '')[:80]
    platform = p.get('platform', '?')
    dropship = p.get('is_dropship', False)
    imgs = len(p.get('image_urls', []))
    
    print(f'{i}. {title}')
    print(f'   Gia: {price} CNY (~{vnd:,} VND) | {imgs} anh')
    print(f'   Shop: {supplier} | Rating: {rating}')
    print(f'   Link: {url}')
    print(f'   Platform: {platform} | Dropship: {dropship}')
    print()
