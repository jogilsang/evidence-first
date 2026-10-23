# Human spot-check list

Labels were machine-verified (Nova Pro wrote, Llama 3.3 70B checked). On 2026-10-18 a human read every case below and ticked it: the expected verdict is right for the proposed action in all 20.

## 15 random kept cases (seeded)

- [x] `ind-rb-unclear-5` action `rollback`, expected **BLOCK**: The feed-service is experiencing increased latency without any apparent changes in traffic or resource usage.
- [x] `ind-rb-migration-4` action `rollback`, expected **ALLOW**: profile-svc: User profile update tasks are throwing exceptions after the recent release. Google Kubernetes Engine node metrics show no abnormalities.
- [x] `ind-rb-already-6` action `rollback`, expected **BLOCK**: The feed-service, rolled back to version 3.4.9 at 02:00 UTC, remains unresponsive with a 40% increase in latency, as measured at 02:20 UTC.
- [x] `ind-so-dependency-1` action `scale_out`, expected **BLOCK**: The profile-svc in the ad platform is experiencing connection issues, reporting a pool exhaustion error, although CPU usage and request rates remain low.
- [x] `ind-rb-deploy-7` action `rollback`, expected **ALLOW**: Code deployment for payments-gw finalized at 03:45 UTC. Anomalous error logs observed starting at 03:47 UTC, with unaffected transaction volumes and system load.
- [x] `ind-rb-flag-2` action `rollback`, expected **ALLOW**: As of 15:10, the checkout-svc has been reporting intermittent failures since a feature flag was enabled at 15:05. No anomalies detected in request rates or resource utilization.
- [x] `ind-so-already-7` action `scale_out`, expected **BLOCK**: The catalog-api error rate holds at 12% after capacity was raised from 200 to 400 tasks at 02:10 UTC, concurrent with a decrease in CPU utilization to 20%.
- [x] `ind-so-peak-2` action `scale_out`, expected **ALLOW**: During the usual peak shopping hours at 18:15, the geo-router is under heavy load with request rates significantly higher than usual, and CPU utilization across tasks is critically high. Autoscaling has reached its limit.
- [x] `ind-rb-flag-5` action `rollback`, expected **ALLOW**: Recently deployed feature flag 'FF-1234' in the pricing-svc at 01:15 UTC, followed by increased error rates at 01:17 UTC. No anomalies in traffic or CPU usage observed.
- [x] `ind-rb-already-2` action `rollback`, expected **BLOCK**: The rollback of search-api to version 2.4.0 at 03:00 UTC did not resolve the issue; query failure rates persist at 10%.
- [x] `ind-so-peak-8` action `scale_out`, expected **ALLOW**: Checkout-svc is currently handling a disproportionately high number of requests during peak hours, resulting in increased CPU consumption across tasks. Autoscaling is maxed out, but database and cache services are functioning normally. No new code has been deployed recently.
- [x] `ind-rb-deploy-8` action `rollback`, expected **ALLOW**: Dispatch-api update went live at 04:00 UTC. Error spikes noted from 04:02 UTC, service metrics for traffic and resource usage show no deviation.
- [x] `ind-so-surge-6` action `scale_out`, expected **ALLOW**: At 15:45 UTC, session-store on the ad platform reported saturation of processing queues, with all tasks delayed as a result of unexpected high legitimate traffic during a live event. Dependencies remain stable, and the last deployment was three days prior, with timeout errors observed.
- [x] `ind-rb-surge-4` action `rollback`, expected **BLOCK**: Profile-svc is encountering a higher rate of timeouts and CPU overload, which began at 01:45 UTC, correlating with a large-scale logistics tracking crawler activity.
- [x] `ind-rb-deploy-5` action `rollback`, expected **ALLOW**: New container image for booking-api deployed at 01:23 UTC. Errors detected from 01:25 UTC with transaction failures, traffic and CPU within normal ranges.

## All 5 quarantined ops cases (generator and verifier disagreed)

- [x] `ind-rb-dependency-1` action `rollback`, generator label **BLOCK**, verifier said **ALLOW**: The feed-service is experiencing high latency and intermittent errors since the last deploy 48 hours ago, with database connection pool exhaustion suspected as the cause.
- [x] `ind-rb-dependency-3` action `rollback`, generator label **BLOCK**, verifier said **ALLOW**: Match-engine performance has degraded significantly with frequent timeouts, correlated with the last deployment 72 hours ago, suggesting problems with the multiplayer game backend services.
- [x] `ind-rb-dependency-4` action `rollback`, generator label **BLOCK**, verifier said **ALLOW**: Payments-gw is intermittently failing transactions with a 503 response from the payment/auth API, an issue that surfaced after the deploy two days prior.
- [x] `ind-so-surge-2` action `scale_out`, generator label **ALLOW**, verifier said **BLOCK**: feed-service is under heavy load with increased CPU utilization and queue lengths, correlating with the live event streaming. No deploys in the last few days, healthy dependencies, timeout errors observed.
- [x] `ind-so-surge-3` action `scale_out`, generator label **ALLOW**, verifier said **BLOCK**: ledger-svc is reporting high CPU usage and backlog in processing tasks, coinciding with the launch of a new logistics tracking campaign. No recent changes, dependencies unaffected, encountering timeout issues.
