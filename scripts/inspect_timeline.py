"""Read-only Resolve 21.1 inventory. Submit this source to MCP run_script.

Requires injected `resolve`. Adjust ITEM_OFFSET / ITEM_LIMIT for pagination.
Never selects or modifies projects, timelines or clips.
"""

ITEM_OFFSET = 0
ITEM_LIMIT = 100

current_project = resolve.GetProjectManager().GetCurrentProject()
current_timeline = current_project.GetCurrentTimeline() if current_project else None
result = {"version": resolve.GetVersionString(), "project": None, "timeline": None}
if current_project:
    result["project"] = {
        "id": current_project.GetUniqueId(), "name": current_project.GetName(),
        "timeline_count": current_project.GetTimelineCount(),
    }
if current_timeline:
    settings = current_timeline.GetSettings()
    inventory = {
        "id": current_timeline.GetUniqueId(), "name": current_timeline.GetName(),
        "start_frame": current_timeline.GetStartFrame(),
        "end_frame": current_timeline.GetEndFrame(),
        "start_timecode": current_timeline.GetStartTimecode(),
        "settings": {k: settings.get(k) for k in (
            "timelineFrameRate", "timelineDropFrameTimecode",
            "timelineResolutionWidth", "timelineResolutionHeight",
        )},
        "tracks": [], "items": [],
    }
    item_number = 0
    for track_type in ("video", "audio", "subtitle"):
        for index in range(1, current_timeline.GetTrackCount(track_type) + 1):
            track_items = current_timeline.GetItemListInTrack(track_type, index) or []
            inventory["tracks"].append({
                "type": track_type, "index": index,
                "name": current_timeline.GetTrackName(track_type, index),
                "count": len(track_items),
                "locked": current_timeline.GetIsTrackLocked(track_type, index),
            })
            for item in track_items:
                item_number += 1
                if not ITEM_OFFSET < item_number <= ITEM_OFFSET + ITEM_LIMIT:
                    continue
                row = {
                    "id": item.GetUniqueId(), "name": item.GetName(),
                    "track_type": track_type, "track_index": index,
                    "start": item.GetStart(), "end": item.GetEnd(),
                    "duration": item.GetDuration(),
                }
                if track_type in ("video", "audio"):
                    row["type"] = item.GetType()
                    media = item.GetMediaPoolItem()
                    if media:
                        props = media.GetClipProperty()
                        row["media"] = {
                            "id": media.GetUniqueId(), "path": props.get("File Path"),
                            "fps": props.get("FPS"), "frames": props.get("Frames"),
                        }
                        row["source_in"] = item.GetSourceStartFrame()
                        row["source_out"] = item.GetSourceEndFrame()
                        row["speed"] = item.GetSpeed()
                        row["fades"] = item.GetFades()
                inventory["items"].append(row)
    inventory["total_items"] = item_number
    inventory["offset"] = ITEM_OFFSET
    inventory["has_more"] = item_number > ITEM_OFFSET + ITEM_LIMIT
    result["timeline"] = inventory
