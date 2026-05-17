### Naming Convetions
Trong phần logical này, ta sẽ định nghĩa behavior của xe
- logical\maneuvers\type sẽ được lấy giống với Maneuver_blocks\cutin*\Event_Name 
 ~~ phần detail block sẽ được thay thế đúng với logical: cutin, cutout,....
* logical\actors sẽ bao gồm:
    + ev {type: ego}
    + tv1 {
        {type: car,truck,bus,...},
        {lane: ego, left, right},
        {position: front_ego, front_tv, behind, next_to_ego,}, {state: moving, static}
        }

* logical\maneuvers sẽ bao gồm:
    - type: event_name + actor
        { Các event_name hiện tại:
            + cutin_event
            + cutout_event
            + follow_slowdown
            + follow_stable
            + follow_resume
            + appear_event
            + curve_event
            + ego_cutout_event
            + ego_cutout_signal_event
            + stop_event
            + resume_event
            + cruise_event
            }
    