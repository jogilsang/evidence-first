# Can you fool the gate?

Honest gallery: the cases where the shipped policy gets it wrong, and the perturbations that flip a verdict that was right.
Try your own with `python play.py "<log>" rollback` (needs the local Decider; no AWS calls).

## 1. Misses on independent cases

**`ind-rb-surge-3`** (expected BLOCK, gate said ALLOW)

> Match-engine is reporting timeout errors and high CPU usage following a spike in traffic, possibly from increased multiplayer game activity after the last deployment two days ago.

Gate reason: _evidence supports 'rollback'_

**`ind-rb-surge-8`** (expected BLOCK, gate said ALLOW)

> ranker-api has seen a dramatic rise in CPU usage and timeout errors, with request rates tripling in the past hour. The last deployment was three days ago, prior to the start of the current traffic surge.

Gate reason: _evidence supports 'rollback'_

**`ind-rb-dependency-8`** (expected BLOCK, gate said ALLOW)

> Pricing-svc is unable to retrieve updated product prices, resulting in stale pricing data being served to customers. The external pricing API is returning 503 errors, and the last deploy occurred 48 hours ago.

Gate reason: _evidence supports 'rollback'_

**`ind-so-already-3`** (expected BLOCK, gate said ALLOW)

> 11:00 UTC: Profile-svc error rates stay constant at 18% following the increase of task counts from 20 to 40 at 10:30 UTC within the healthcare scheduling domain. CPU is now at 25%.

Gate reason: _evidence supports 'scale_out'_

## 2. Perturbations that flip a correct verdict

13 flips across 4 perturbation kinds (typos, reorder, noise, korean).

- **typos** on `ind-rb-migration-2` (expected ALLOW): payments-gw: Transaction processing tasks are failing with SQL errors since the recent schema migration. All Azure SQL Database metircs appear nominal.
- **noise** on `ind-rb-deploy-4` (expected ALLOW): 10:02:11 health-check /ping 200 OK (3 ms) 10:02:31 metrics exporter flushed 214 series 10:02:55 config reload: no changes detected 03:25 UTC - The media-edge service update concluded at 03:10 UTC, and since then, we've detected a rise in error occurrences, despite normal operational metrics for tra…
- **noise** on `ind-rb-deploy-8` (expected ALLOW): 10:02:14 cert-renewal job finished, next run in 29 days 10:03:02 disk usage /var/log 41% 10:02:11 health-check /ping 200 OK (3 ms) Dispatch-api update went live at 04:00 UTC. Error spikes noted from 04:02 UTC, service metrics for traffic and resource usage show no deviation. 10:02:31 metrics export…
- **noise** on `ind-rb-flag-6` (expected ALLOW): 10:03:09 ntp offset 0.4 ms 10:02:14 cert-renewal job finished, next run in 29 days 10:02:55 config reload: no changes detected An environment variable 'MEDIA_CACHE_TIMEOUT' was updated in the media-edge service at 02:05 UTC. Errors started occurring at 02:07 UTC, despite normal dependency response …
- **noise** on `ind-rb-flag-8` (expected ALLOW): 10:02:14 cert-renewal job finished, next run in 29 days 10:02:55 config reload: no changes detected 10:03:09 ntp offset 0.4 ms Feature flag 'GEO_ROUTE_OPTIMIZATION' enabled in the geo-router at 04:45 UTC. Error rate increased at 04:47 UTC, no deviations in traffic patterns or service latencies note…
- **noise** on `ind-rb-migration-2` (expected ALLOW): 10:02:11 health-check /ping 200 OK (3 ms) 10:03:09 ntp offset 0.4 ms 10:02:31 metrics exporter flushed 214 series payments-gw: Transaction processing tasks are failing with SQL errors since the recent schema migration. All Azure SQL Database metrics appear nominal. 10:02:20 gc pause 12 ms (young ge…
- **noise** on `ind-rb-migration-3` (expected ALLOW): 10:03:02 disk usage /var/log 41% 10:03:09 ntp offset 0.4 ms 10:02:11 health-check /ping 200 OK (3 ms) media-edge: Image processing jobs are crashing with library import errors post the latest library upgrade. GCP Cloud Functions metrics are stable. 10:02:14 cert-renewal job finished, next run in 29…
- **noise** on `ind-rb-migration-4` (expected ALLOW): 10:02:20 gc pause 12 ms (young generation) 10:02:14 cert-renewal job finished, next run in 29 days 10:02:55 config reload: no changes detected profile-svc: User profile update tasks are throwing exceptions after the recent release. Google Kubernetes Engine node metrics show no abnormalities. 10:03:…
- **noise** on `ind-rb-migration-6` (expected ALLOW): 10:02:11 health-check /ping 200 OK (3 ms) 10:02:20 gc pause 12 ms (young generation) 10:03:09 ntp offset 0.4 ms 09:15 UTC - inventory-sync: Recent schema migration seems to have caused data sync tasks to fail. Error messages point to incompatibilities with the new database structure. 10:03:02 disk …
- **korean** on `ind-rb-migration-2` (expected ALLOW): payments-gw: 최근 스키마 마이그레이션 이후 SQL 오류로 인해 거래 처리 작업이 실패하고 있습니다. 모든 Azure SQL Database 메트릭은 정상으로 나타나고 있습니다.

## 3. Try it

```bash
python play.py --examples          # a few cases, including known misses
python play.py "<log>" rollback
python play.py "<ticket>" refund --domain refund
```
