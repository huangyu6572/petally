-- ============================================================
-- 🌸 Petal Demo 数据初始化脚本
-- 用途: 为三大功能模块填充可验证的演示数据
-- 执行: psql -U petal -d petal -f seed_demo.sql
-- ============================================================

-- 清空旧数据（开发环境）
TRUNCATE TABLE promo_clicks, coupons, promotions, skin_analyses,
               anti_fake_codes, products, users
               RESTART IDENTITY CASCADE;

-- ──────────────────────────────────────────────────────────────
-- 1. 测试用户（绕过微信登录，直接插入）
-- ──────────────────────────────────────────────────────────────
INSERT INTO users (openid, nickname, avatar_url, created_at, updated_at) VALUES
  ('demo_openid_001', '测试用户A', 'https://picsum.photos/seed/userA/100', NOW(), NOW()),
  ('demo_openid_002', '测试用户B', 'https://picsum.photos/seed/userB/100', NOW(), NOW());

-- ──────────────────────────────────────────────────────────────
-- 2. 商品数据
-- ──────────────────────────────────────────────────────────────
INSERT INTO products (name, brand, category, description, price, tags, status, created_at, updated_at) VALUES
  ('花瓣玻尿酸精华水', 'Petal', 'skincare',
   '深层补水，持续12小时保湿，适合所有肤质',
   299.00, '["保湿","补水","透明质酸","敏感肌适用"]', 1, NOW(), NOW()),

  ('Petal 控油清爽乳液', 'Petal', 'skincare',
   '轻盈不油腻，持效控油8小时，哑光效果',
   199.00, '["控油","清爽","哑光","混合肌"]', 1, NOW(), NOW()),

  ('花瓣美白淡斑精华', 'Petal', 'serum',
   '烟酰胺+维C双重美白，淡化色斑提亮肤色',
   459.00, '["美白","淡斑","烟酰胺","维C"]', 1, NOW(), NOW()),

  ('Petal 修护舒缓面膜', 'Petal', 'mask',
   '积雪草苷+神经酰胺，敏感修护，镇静泛红',
   168.00, '["舒缓","修护","敏感肌专用","神经酰胺"]', 1, NOW(), NOW()),

  ('花瓣胶原蛋白紧致霜', 'Petal', 'cream',
   '三重胜肽+胶原蛋白，抗皱紧致，淡化细纹',
   589.00, '["抗皱","紧致","胶原蛋白","视黄醇"]', 1, NOW(), NOW());

-- ──────────────────────────────────────────────────────────────
-- 3. 防伪码数据（功能一：防伪查询）
--    状态: unused(未查询) / verified(已查询) / warning(多次查询)
-- ──────────────────────────────────────────────────────────────
INSERT INTO anti_fake_codes
  (code, code_hash, product_id, batch_no, is_verified, query_count, status, created_at) VALUES

  -- ✅ 正品码，从未被查询（字符集: A-H(无I), J-K(无L), M-N(无O), P-Z, 2-9, 连字符）
  ('PET-2B2G4R-A7X9K3M2-Q',
   md5('PET-2B2G4R-A7X9K3M2-Q'),
   1, 'B20260301', FALSE, 0, 'unused', NOW()),

  -- ✅ 正品码，已被查询1次（首次验证）
  ('PET-3C5H7T-B8Y2N4P6-R',
   md5('PET-3C5H7T-B8Y2N4P6-R'),
   2, 'B20260301', TRUE, 1, 'verified',
   NOW() - INTERVAL '3 days'),

  -- ⚠️  可疑码，已被查询3次（触发 warning）
  ('PET-4D6J8V-C9Z3Q5R7-S',
   md5('PET-4D6J8V-C9Z3Q5R7-S'),
   3, 'B20260215', TRUE, 3, 'warning',
   NOW() - INTERVAL '10 days'),

  -- 🆕 全新正品码（花瓣面膜）
  ('PET-5F7K9W-D2X4T6U8-V',
   md5('PET-5F7K9W-D2X4T6U8-V'),
   4, 'B20260320', FALSE, 0, 'unused', NOW()),

  -- ✅ 正品码（花瓣紧致霜）
  ('PET-6G8M2Y-E3W5V7T9-X',
   md5('PET-6G8M2Y-E3W5V7T9-X'),
   5, 'B20260310', FALSE, 0, 'unused', NOW());

-- ──────────────────────────────────────────────────────────────
-- 4. 推广活动数据（功能三：商品推广）
-- ──────────────────────────────────────────────────────────────
INSERT INTO promotions
  (title, description, product_id, promo_type, discount_value,
   min_purchase, stock, start_time, end_time, status, created_at) VALUES

  -- 7折活动（进行中）
  ('花瓣精华水 7折特惠',
   '限时7折，买完即止，每人限购2件',
   1, 'discount', 0.7, NULL,
   500, NOW() - INTERVAL '1 day', NOW() + INTERVAL '7 days',
   2, NOW()),

  -- 满减券（进行中）
  ('满200减50优惠券',
   '购买任意护肤品满200元立减50元',
   2, 'coupon', 50.00, 200.00,
   200, NOW() - INTERVAL '2 days', NOW() + INTERVAL '14 days',
   2, NOW()),

  -- 新人专享（进行中）
  ('新人专享：精华立减80',
   '新注册用户专享，淡斑精华直减80元',
   3, 'new_user', 80.00, NULL,
   100, NOW() - INTERVAL '1 day', NOW() + INTERVAL '30 days',
   2, NOW()),

  -- AI推荐专属活动（进行中）
  ('AI肌肤分析专属推荐',
   '完成AI肌肤分析后可解锁专属折扣',
   4, 'ai_recommend', 0.85, NULL,
   300, NOW() - INTERVAL '1 day', NOW() + INTERVAL '15 days',
   2, NOW()),

  -- 即将开始的活动
  ('花瓣紧致霜预售活动',
   '5折预售，仅限前100名',
   5, 'flash_sale', 0.5, NULL,
   100, NOW() + INTERVAL '3 days', NOW() + INTERVAL '10 days',
   1, NOW());

-- ──────────────────────────────────────────────────────────────
-- 5. 肌肤分析示例数据（功能二：AI肌肤分析）
-- ──────────────────────────────────────────────────────────────
INSERT INTO skin_analyses
  (id, user_id, image_url, analysis_type, overall_score, skin_type,
   analysis_result, suggestions, model_version, status, created_at)
VALUES
  ('ana_20260401_demo001', 1,
   '/2026/04/01/1/ana_20260401_demo001.jpg',
   'face_full', 72, 'combination',
   '[
     {"type":"acne","severity":"mild","score":65,"label":"痘痘/粉刺","description":"T区有少量痘痘","regions":[]},
     {"type":"oiliness","severity":"moderate","score":55,"label":"出油/油光","description":"T区油脂分泌较旺盛","regions":[]},
     {"type":"pore","severity":"mild","score":70,"label":"毛孔粗大","description":"鼻翼两侧毛孔较明显","regions":[]}
   ]'::jsonb,
   '[
     {"category":"skincare","title":"温和清洁","content":"使用氨基酸洁面乳，每天早晚各一次","priority":1},
     {"category":"skincare","title":"控油精华","content":"T区使用含烟酰胺的控油精华","priority":2},
     {"category":"lifestyle","title":"饮食调整","content":"减少高糖高油食物摄入","priority":3}
   ]'::jsonb,
   'skin-v2.1', 1, NOW() - INTERVAL '2 days'),

  ('ana_20260330_demo002', 1,
   '/2026/03/30/1/ana_20260330_demo002.jpg',
   'face_full', 68, 'oily',
   '[
     {"type":"acne","severity":"moderate","score":50,"label":"痘痘/粉刺","description":"额头和下巴痘痘较多","regions":[]},
     {"type":"oiliness","severity":"moderate","score":52,"label":"出油/油光","description":"全脸出油明显","regions":[]}
   ]'::jsonb,
   '[
     {"category":"skincare","title":"深层清洁","content":"每周1-2次使用泥膜深层清洁毛孔","priority":1},
     {"category":"skincare","title":"水杨酸精华","content":"局部使用含水杨酸的祛痘精华","priority":2}
   ]'::jsonb,
   'skin-v2.1', 1, NOW() - INTERVAL '5 days');

-- ──────────────────────────────────────────────────────────────
-- 验证结果
-- ──────────────────────────────────────────────────────────────
SELECT '数据初始化完成！' AS status;
SELECT 'users'         AS "表名", count(*) AS "记录数" FROM users
UNION ALL
SELECT 'products',      count(*) FROM products
UNION ALL
SELECT 'anti_fake_codes', count(*) FROM anti_fake_codes
UNION ALL
SELECT 'promotions',    count(*) FROM promotions
UNION ALL
SELECT 'skin_analyses', count(*) FROM skin_analyses;
