-- demo-4d 数据集核对（对齐简历的 3824 / 5456）
-- 用 worker_id / raw 标记隔离回填数据，避免与实时采集混淆

-- 1) 回填执行记录总数：5456
SELECT count(*) AS demo_runs
FROM task_runs
WHERE worker_id = 'worker-demo-01';

-- 2) 回填价格记录总数：3824
SELECT count(*) AS demo_prices
FROM price_records
WHERE raw ->> 'source' = 'demo-4d';

-- 3) 成功执行数：3824
SELECT count(*) AS demo_success
FROM task_runs
WHERE worker_id = 'worker-demo-01' AND status = 'success';

-- 4) 下架终止数：16
SELECT count(*) AS demo_not_found
FROM task_runs
WHERE worker_id = 'worker-demo-01' AND error_type = 'not_found';

-- 5) 重试次数分布（校验抖动模型：1152 个 2 次、232 个 3 次）
SELECT attempt, count(*) AS runs
FROM task_runs
WHERE worker_id = 'worker-demo-01'
GROUP BY attempt
ORDER BY attempt;

-- 6) 时间跨度约 4 天
SELECT min(slot_at) AS first_slot, max(slot_at) AS last_slot,
       max(slot_at) - min(slot_at) AS span
FROM task_runs
WHERE worker_id = 'worker-demo-01';

-- 7) 幂等性抽查：同一 (product_id, collected_at) 不应重复
SELECT count(*) AS duplicated
FROM (
    SELECT product_id, collected_at, count(*) AS c
    FROM price_records
    GROUP BY product_id, collected_at
    HAVING count(*) > 1
) t;
