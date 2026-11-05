#!/usr/bin/env python3
"""Build the web-port resource tree for Buckshot Roulette.

Strategy (replaces the failed pruning approach):

The extracted game_data/ IS the original PCK content. Godot's exported PCK
relies on `.import` sidecars to remap `res://foo.png` -> `res://.godot/imported/...`
and on `.godot/global_script_class_cache.cfg` for class_name resolution.
Previous attempts dropped those files and broke resource loading.

So: copy the FULL tree, overlay the already-shrunk/re-encoded imported assets
(build/assets), then make exactly two web-specific changes:

  1. add scripts/SteamWeb.gd  - a no-op stand-in for the GodotSteam singleton
     (the desktop build had Steam compiled in; web cannot)
  2. project.binary - register autoload `Steam` -> scripts/SteamWeb.gd
     (autoload `GlobalSteam` -> scripts/Steam.gd is left exactly as shipped)
"""
import os
import re
import shutil
import struct
import sys

ROOT = r"C:\Users\eight\Downloads\Buckshot Roulette_windows\webport\game_data"
OUT = r"C:\Users\eight\Downloads\Buckshot Roulette_windows\webport\build\full"
ASSETS = r"C:\Users\eight\Downloads\Buckshot Roulette_windows\webport\build\assets"

STEAMWEB_GD = r'''extends Node

# Web stand-in for the GodotSteam singleton.
# The desktop build has Steam compiled into the engine; the web build cannot,
# so every method the game scripts call is stubbed here as a no-op that
# returns a safe default. Autoload registered as "Steam" in project.binary.

# ---- signals the scripts connect to -----------------------------------------
signal lobby_created(connect_request)
signal lobby_joined(lobby_id, permissions)
signal lobby_chat_update(lobby_id)
signal lobby_match_list(lobbies)
signal persona_state_change()
signal p2p_session_request(remote_id)
signal p2p_session_connect_fail(remote_id, error)
signal join_requested(lobby_id)
signal avatar_loaded(steam_id, avatar, width_height)
signal leaderboard_find_result(handle)
signal leaderboard_score_uploaded(handle, result)
signal leaderboard_scores_downloaded(handle, result, entries)

# ---- constants used by game scripts ------------------------------------------
const LEADERBOARD_DATA_REQUEST_GLOBAL = 0
const LEADERBOARD_DATA_REQUEST_GLOBAL_AROUND_USER = 1
const LEADERBOARD_DATA_REQUEST_FRIENDS = 2

const LOBBY_TYPE_PRIVATE = 0
const LOBBY_TYPE_FRIENDS_ONLY = 1
const LOBBY_TYPE_PUBLIC = 2
const LOBBY_TYPE_INVISIBLE = 3

const LOBBY_DISTANCE_FILTER_CLOSE = 0
const LOBBY_DISTANCE_FILTER_DEFAULT = 1
const LOBBY_DISTANCE_FILTER_FAR = 2
const LOBBY_DISTANCE_FILTER_WORLDWIDE = 3

const P2P_SEND_RELIABLE = 0
const P2P_SEND_UNRELIABLE = 1

const CHAT_MEMBER_STATE_CHANGE_ENTERED = 1
const CHAT_MEMBER_STATE_CHANGE_LEFT = 2
const CHAT_MEMBER_STATE_CHANGE_DISCONNECTED = 4
const CHAT_MEMBER_STATE_CHANGE_KICKED = 8
const CHAT_MEMBER_STATE_CHANGE_BANNED = 16

const CHAT_ROOM_ENTER_RESPONSE_SUCCESS = 1
const CHAT_ROOM_ENTER_RESPONSE_DOESNT_EXIST = 2
const CHAT_ROOM_ENTER_RESPONSE_NOT_ALLOWED = 3
const CHAT_ROOM_ENTER_RESPONSE_FULL = 4
const CHAT_ROOM_ENTER_RESPONSE_ERROR = 5
const CHAT_ROOM_ENTER_RESPONSE_BANNED = 6
const CHAT_ROOM_ENTER_RESPONSE_LIMITED = 7
const CHAT_ROOM_ENTER_RESPONSE_CLAN_DISABLED = 8
const CHAT_ROOM_ENTER_RESPONSE_COMMUNITY_BAN = 9
const CHAT_ROOM_ENTER_RESPONSE_MEMBER_BLOCKED_YOU = 10
const CHAT_ROOM_ENTER_RESPONSE_YOU_BLOCKED_MEMBER = 11

# ---- core ---------------------------------------------------------------------
func _ready():
	print("SteamWeb: stub loaded (Steam API not available on web)")

func steamInit(_notify: bool = false) -> Dictionary:
	print("SteamWeb: steamInit -> not available on web")
	return {"status": 255}

func run_callbacks():
	pass

func loggedOn() -> bool:
	return false

func getSteamID() -> int:
	return 0

func getPersonaName() -> String:
	return "Web Player"

func getFriendPersonaName(_steam_id: int) -> String:
	return "Player"

func isSteamRunningOnSteamDeck() -> bool:
	return false

# ---- achievements / stats ------------------------------------------------------
func setAchievement(_achievement_name: String):
	pass

func clearAchievement(_achievement_name: String):
	pass

func storeStats():
	pass

# ---- leaderboards ---------------------------------------------------------------
func setLeaderboardDetailsMax(_max: int) -> int:
	return 0

func findLeaderboard(_leaderboard_name: String):
	pass

func uploadLeaderboardScore(_score: int, _keep_best: bool, _details: Array, _handle):
	pass

func downloadLeaderboardEntries(_start: int, _end: int, _request_type: int):
	pass

func getLeaderboardEntryCount(_handle: int) -> int:
	return 0

# ---- lobbies --------------------------------------------------------------------
func createLobby(_type: int, _max_members: int) -> int:
	return 0

func joinLobby(_lobby_id: int) -> int:
	return 255

func leaveLobby(_lobby_id: int):
	pass

func setLobbyData(_lobby_id: int, _key: String, _value: String):
	pass

func getLobbyData(_lobby_id: int, _key: String) -> String:
	return ""

func setLobbyType(_lobby_id: int, _type: int):
	pass

func setLobbyJoinable(_lobby_id: int, _joinable: bool):
	pass

func setLobbyMemberLimit(_lobby_id: int, _max_members: int):
	pass

func getNumLobbyMembers(_lobby_id: int) -> int:
	return 0

func getLobbyMemberByIndex(_lobby_id: int, _member: int) -> int:
	return 0

func getLobbyOwner(_lobby_id: int) -> int:
	return 0

func inviteUserToLobby(_lobby_id: int, _steam_id: int):
	pass

func sendChatMessage(_lobby_id: int, _message: String):
	pass

func addRequestLobbyListDistanceFilter(_filter: int):
	pass

func addRequestLobbyListResultCountFilter(_count: int):
	pass

func requestLobbyList():
	pass

func activateGameOverlayInviteDialog(_lobby_id: int):
	pass

func getPlayerAvatar(_avatar_size: int, _steam_id: int) -> Dictionary:
	return {}

# ---- P2P networking ----------------------------------------------------------------
func sendP2PPacket(_remote_id: int, _data, _send_type: int = 0, _channel: int = 0) -> bool:
	return false

func getAvailableP2PPacketSize(_channel: int = 0) -> int:
	return 0

func readP2PPacket(_max_size: int = 0, _channel: int = 0) -> Dictionary:
	return {"data": PackedByteArray(), "size": 0}

func acceptP2PSessionWithUser(_remote_id: int):
	pass

func closeP2PSessionWithUser(_remote_id: int):
	pass

func allowP2PPacketRelay(_allow: bool = true):
	pass
'''


def decode_ecfg(blob):
    assert blob[:4] == b"ECFG", "not an ECFG project.binary"
    count = struct.unpack_from("<I", blob, 4)[0]
    p = 8
    entries = []
    for _ in range(count):
        slen = struct.unpack_from("<I", blob, p)[0]; p += 4
        key = blob[p:p + slen].decode("utf-8"); p += slen
        vlen = struct.unpack_from("<I", blob, p)[0]; p += 4
        entries.append((key, blob[p:p + vlen])); p += vlen
    assert p == len(blob), "trailing bytes in project.binary"
    return entries


def encode_str(s):
    raw = s.encode("utf-8") + b"\x00"
    pad = (4 - (len(raw) % 4)) % 4
    return struct.pack("<II", 4, len(raw)) + raw + b"\x00" * pad


def main():
    # 1. full copy of the extracted PCK content
    if os.path.exists(OUT):
        print("removing old", OUT)
        shutil.rmtree(OUT)
    print("copying full tree...")
    shutil.copytree(ROOT, OUT)
    print("  done")

    # 2. overlay shrunk textures + re-encoded audio (same res paths, smaller bytes)
    print("overlaying build/assets...")
    n = 0
    for dp, _dn, fn in os.walk(ASSETS):
        for f in fn:
            src = os.path.join(dp, f)
            rel = os.path.relpath(src, ASSETS)
            dst = os.path.join(OUT, rel)
            os.makedirs(os.path.dirname(dst), exist_ok=True)
            shutil.copy2(src, dst)
            n += 1
    print(f"  overlaid {n} files")

    # 3. SteamWeb stub
    stub_path = os.path.join(OUT, "scripts", "SteamWeb.gd")
    with open(stub_path, "w", encoding="utf-8") as f:
        f.write(STEAMWEB_GD)
    print("wrote scripts/SteamWeb.gd")

    # 4. project.binary: register autoload Steam -> SteamWeb.gd (single change)
    proj = os.path.join(OUT, "project.binary")
    entries = decode_ecfg(open(proj, "rb").read())
    keys = [k for k, _ in entries]
    assert "autoload/GlobalSteam" in keys, "GlobalSteam autoload missing"
    assert "autoload/Steam" not in keys, "autoload/Steam already present"
    last_auto = max(i for i, (k, _) in enumerate(entries) if k.startswith("autoload/"))
    entries.insert(last_auto + 1, ("autoload/Steam", encode_str("*res://scripts/SteamWeb.gd")))
    out = bytearray(b"ECFG")
    out += struct.pack("<I", len(entries))
    for k, blob in entries:
        kb = k.encode("utf-8")
        out += struct.pack("<I", len(kb)) + kb
        out += struct.pack("<I", len(blob)) + blob
    with open(proj, "wb") as f:
        f.write(out)
    print(f"patched project.binary: {len(entries)} entries, autoload/Steam -> SteamWeb.gd")

    # 5. sizes
    total = 0
    for dp, _dn, fn in os.walk(OUT):
        for f in fn:
            total += os.path.getsize(os.path.join(dp, f))
    print(f"build/full: {total / 1e6:.1f} MB")


if __name__ == "__main__":
    sys.exit(main())