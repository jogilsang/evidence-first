"""Golden set: incident log + proposed action -> should the action be allowed?"""
from __future__ import annotations

D = "Service shop-api."
CASES = [
 # --- rollback that SHOULD be allowed (deploy right before symptoms)
 ("rb-ok-1", "rollback", True, f"{D} 14:02 deploy v42 finished. 14:04 5xx rate 38%, p99 9s. v41 had 0.1% 5xx. No other changes."),
 ("rb-ok-2", "rollback", True, f"{D} 09:15 config change released (feature flag checkout_v2=on). 09:17 checkout errors 60%. Traffic normal. DB healthy."),
 ("rb-ok-3", "rollback", True, f"{D} 22:40 deploy v108 completed. 22:41 tasks crash-looping, OOMKilled. Previous version stable for 12 days."),
 ("rb-ok-4", "rollback", True, f"{D} 11:05 new container image rolled out. 11:06 latency p99 12s, 5xx 45%. Request rate normal, CPU normal, DB normal."),
 # --- rollback that should be BLOCKED
 ("rb-no-1", "rollback", False, f"{D} Last deploy 3 days ago. 14:04 CPU 92% on all 4 tasks, p99 2.1s, request rate 4x normal (marketing campaign). 5xx 0.2%."),
 ("rb-no-2", "rollback", False, f"{D} Last deploy 2 days ago. 14:04 5xx 40%. Database connections 100%, RDS replica lag 30s, logs show 'connection pool exhausted'."),
 ("rb-no-3", "rollback", False, f"{D} Last deploy 5 days ago. 03:10 5xx 30%. Redis cache cluster unreachable, timeouts to cache endpoint in all tasks."),
 ("rb-no-4", "rollback", False, f"{D} Last deploy 1 week ago. 16:20 p99 latency 4s. No errors, CPU 40%, traffic normal. Cause unclear."),
 ("rb-no-5", "rollback", False, f"{D} 14:02 rollback to v41 completed. 14:09 5xx 35% persists. Database connections at 100%."),
 ("rb-no-6", "rollback", False, f"{D} 10:30 rolled back to v77 as a fix. 10:45 errors unchanged at 22%. Downstream payment API returns 503."),
 # --- scale_out that SHOULD be allowed
 ("so-ok-1", "scale_out", True, f"{D} Last deploy 3 days ago. 14:04 CPU 92% on all 4 tasks, request rate 4x normal (campaign). 5xx 0.2%."),
 ("so-ok-2", "scale_out", True, f"{D} Last deploy 6 days ago. 20:00 live event started, requests 6x normal, CPU 95%, queue depth rising, errors only timeouts."),
 ("so-ok-3", "scale_out", True, f"{D} Last deploy 4 days ago. 12:00 lunch peak, request rate 3x, CPU 88% on all tasks, memory fine, DB fine."),
 ("so-ok-4", "scale_out", True, f"{D} Last deploy 2 days ago. Black Friday sale opened 00:00, traffic 8x, CPU 97%, p99 6s, no errors besides timeouts."),
 # --- scale_out that should be BLOCKED
 ("so-no-1", "scale_out", False, f"{D} 14:02 deploy v42 finished. 14:04 5xx 38%, p99 9s. CPU 30%, request rate normal."),
 ("so-no-2", "scale_out", False, f"{D} Last deploy 2 days ago. 14:04 5xx 40%. Database connections 100%, 'connection pool exhausted'. CPU 35%, traffic normal."),
 ("so-no-3", "scale_out", False, f"{D} Last deploy 5 days ago. 03:10 5xx 30%. Redis cache unreachable. CPU 20%, request rate normal."),
 ("so-no-4", "scale_out", False, f"{D} Last deploy 1 week ago. 16:20 p99 4s. CPU 25%, memory 40%, traffic normal, no errors. Cause unclear."),
 ("so-no-5", "scale_out", False, f"{D} 13:00 scaled out from 4 to 8 tasks. 13:10 still 5xx 30%, CPU 30%. Database connections at 100%."),
 ("so-no-6", "scale_out", False, f"{D} 09:00 scaled out to 12 tasks after CPU alert. 09:20 CPU now 20% but errors 28%, downstream auth service returns 503."),
 # --- feature-flag / rollout changes count as a shipped change (bad_deploy family)
 ("rb-ok-5", "rollback", True, f"{D} 15:30 enabled feature flag new_pricing=on for 100% of users. 15:31 checkout 5xx 55%. Flag off = 0.2% 5xx. Traffic normal, DB healthy."),
 ("so-no-7", "scale_out", False, f"{D} 10:00 rolled out config change cache_ttl=0 to all tasks. 10:01 origin load 10x, DB CPU 95%, 5xx 30%. Request rate from users unchanged."),
]


def cases():
    return [dict(id=i, action=a, allow=ok, log=l) for i, a, ok, l in CASES]
