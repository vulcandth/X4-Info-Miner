#!/usr/bin/env python3

# Copyright (c) 2025 Mark Boddington
#
# Redistribution and use in source and binary forms, with or without
# modification, are permitted provided that the following conditions
# are met:
# 1. Redistributions of source code must retain the above copyright
#    notice, this list of conditions and the following disclaimer.
# 2. Redistributions in binary form must reproduce the above copyright
#    notice, this list of conditions and the following disclaimer in the
#    documentation and/or other materials provided with the distribution.
# 3. Neither the name of the author nor the names of its contributors may
#    be used to endorse or promote products derived from this software
#
# THIS SOFTWARE IS PROVIDED BY THE AUTHOR AND CONTRIBUTORS "AS IS" AND
# ANY EXPRESS OR IMPLIED WARRANTIES, INCLUDING, BUT NOT LIMITED TO, THE
# IMPLIED WARRANTIES OF MERCHANTABILITY AND FITNESS FOR A PARTICULAR PURPOSE
# ARE DISCLAIMED.  IN NO EVENT SHALL THE AUTHOR OR CONTRIBUTORS BE LIABLE
# FOR ANY DIRECT, INDIRECT, INCIDENTAL, SPECIAL, EXEMPLARY, OR CONSEQUENTIAL
# DAMAGES (INCLUDING, BUT NOT LIMITED TO, PROCUREMENT OF SUBSTITUTE GOODS
# OR SERVICES; LOSS OF USE, DATA, OR PROFITS; OR BUSINESS INTERRUPTION)
# HOWEVER CAUSED AND ON ANY THEORY OF LIABILITY, WHETHER IN CONTRACT, STRICT
# LIABILITY, OR TORT (INCLUDING NEGLIGENCE OR OTHERWISE) ARISING IN ANY WAY
# OUT OF THE USE OF THIS SOFTWARE, EVEN IF ADVISED OF THE POSSIBILITY OF
# SUCH DAMAGE.

from lxml import etree
import gzip
import sys
import argparse
import code
import json
import re
import time
import math
import heapq
from collections import defaultdict

parser = argparse.ArgumentParser()
parser.add_argument("savefile", help="The savegame you want to analyse")
parser.add_argument("-o", "--ownerless", help="Display ownerless ship locations", action="store_true")
parser.add_argument("-l", "--lockboxes", help="Display lockbox locations", action="store_true")
parser.add_argument("-d", "--datavaults", help="Display Data Vault locations", action="store_true")
parser.add_argument("-e", "--erlking", help="Display Erlking Data Vault locations", action="store_true")
parser.add_argument("-c", "--code", help="Display location of the items with code")
parser.add_argument("-p", "--proximity", help="Display The proximity to the closest station", action="store_true")
parser.add_argument("-w", "--whereswally", help="Display player location information", action="store_true")
parser.add_argument("-r", "--wrecks", help="Include wrecks in output", action="store_true")
parser.add_argument("-x", "--xenon", help="Display Xenon ship locations", action="store_true")
parser.add_argument("-k", "--khaak", help="Display Khaak ship locations", action="store_true")
parser.add_argument("-K", "--khaakstations", help="Display Khaak Station locations", action="store_true")
parser.add_argument("-X", "--xml", help="Dump the XML for a specific resource by code")
parser.add_argument("-q", "--quiet", help="Suppress warnings in interactive mode", action="store_true")
parser.add_argument("-i", "--info", help="information level [1-3]. Default is 1 (sector only)", default='1')
parser.add_argument("-f", "--factions", help="Display faction relative strengths", action="store_true")
parser.add_argument("-t", "--trades", help="Display most profitable ware trades. Optional count and max cargo size", nargs='*')
parser.add_argument("--player", help="Use player location, cargo and credits when ranking trades", action="store_true")
parser.add_argument("--distance", help="Rank trades by profit per kilometre", action="store_true")
parser.add_argument("--avoid-illegal-sectors", help="Avoid trades through sectors where the ware is illegal", action="store_true")
parser.add_argument("--avoid-hostile-sectors", help="Avoid trades through sectors hostile to the player", action="store_true")
parser.add_argument("-s", "--shell", help="Starts a python shell to interract with the XML data (read-only)", action="store_true")
args = parser.parse_args()

sectors = []
duplicates = []
warnings = []
sectorCodes = {}
shipCodes = {}
stationCodes = {}
vaultCodes = {}
lockboxCodes = {}
allCodes = {}
sectorNames = {}
allComponents = []
allStations = []
allShips = []
freeShips = []
xenonShips = []
khaakShips = []
khaakStations = []
dataVaults = []
erlkingVaults = []
lockboxes = []
flotsam = []
other = []
ignoredConnections = {}
sector_zone_offsets = {}
sector_macros = {}
stats = {}
phq = None
playerLocation = None
playerMoney = 0
playerCargo = None
trade_buyers = {}
trade_sellers = {}
gates = []
sector_gates = defaultdict(list)
gate_groups = defaultdict(list)
stations = []
nav_graph = {}
station_offset = 0
path_cache = {}
path_map_cache = {}
illegal_factions = set()
illegal_sectors = set()
illegal_nodes = set()
hostile_factions = set()
hostile_sectors = set()
hostile_nodes = set()

if len(sys.argv) < 3:
    parser.print_usage()
    print("\nPlease provide at least 1 argument along with the save file\nUse --help for full help\n")
    sys.exit(1)

print("Loading Savefile....")
start = time.time()
rawxml = None
if args.savefile.endswith(".gz"):
    with gzip.open(args.savefile, 'rb') as f:
        rawxml = f.read()
else:
    with open(args.savefile, 'rb') as f:
        rawxml = f.read()
print('Done. Time: %.2f' % (time.time() - start))

if rawxml is None:
    print("ERROR - Failed to parse savefile")
    sys.exit(1)

# Load the Offset and Naming maps
with open("x4-offsets.json", "r") as jsonfile:
    input = jsonfile.read()
    sector_zone_offsets = json.loads(input)

with open("x4-names.json", "r") as jsonfile:
    input = jsonfile.read()
    sector_macros = json.loads(input)

# Create a custom parser with optimized settings
def create_optimized_parser():
    # Create a parser that's optimized for speed
    parser = etree.XMLParser(
        remove_blank_text=True,        # Removes blank text nodes
        remove_comments=True,          # Ignores comments
        remove_pis=True,               # Removes processing instructions
        huge_tree=True,                # Allows larger trees
        collect_ids=False,             # Don't collect XML IDs
        resolve_entities=False         # Don't resolve entities
    )
    return parser
OPTIMIZED_PARSER = create_optimized_parser()

print("Parsing XML...")
start = time.time()
root = etree.fromstring(rawxml, parser=OPTIMIZED_PARSER)
print('Done. Time: %.2f' % (time.time() - start))

player_info = root.find('./info/player')
if player_info is not None and 'money' in player_info.attrib:
    playerMoney = int(player_info.get('money'))

# Determine which factions are hostile to the player
for rel in root.findall(".//faction[@id='player']/relations/relation"):
    try:
        if float(rel.get('relation', '0')) < -0.25:
            hostile_factions.add(rel.get('faction'))
    except ValueError:
        pass

# Determine which factions enforce illegal wares
for lic in root.findall(".//licence[@type='station_illegal']"):
    for fac in lic.get('factions', '').split():
        illegal_factions.add(fac)

def getDupeObjects(code):
    objects = []
    if code in duplicates:
        for obj in allComponents:
            if obj.get('code') == code:
                obj.set('location', str(getPosition(obj)))
                objects += [ obj ]
    return objects

def getSectors(code):
    objects = getDupeObjects(code)
    if len(objects) < 1:
        if code in sectorCodes:
            objects = [ sectorCodes[code] ]
        elif code in sectorNames:
            objects = [ sectorNames[code] ]
        else:
            print("FAILED: Sector Not found. Check your speeling ;-)")
    return objects

def getShips(code):
    objects = getDupeObjects(code)
    if len(objects) < 1:
        if code in shipCodes:
            ship = shipCodes[code]
            ship.set('location', str(getPosition(ship)))
            objects = [ ship ]
        else:
            print("FAILED: Ship Not found. Check your speeling ;-)")
    return objects

def getObjects(code):
    objects = getDupeObjects(code)
    if len(objects) < 1:
        if code in sectorCodes:
            objects = [ sectorCodes[code] ]
        elif code in sectorNames:
            objects = [ sectorNames[code] ]
        elif code in allCodes:
            obj = allCodes[code]
            obj.set('location', str(getPosition(obj)))
            objects = [ obj ]
        else:
            print("FAILED: object Not found. Check your speeling ;-)")
    return objects

def getStations(code):
    objects = getDupeObjects(code)
    if len(objects) < 1:
        if code in stationCodes:
            station = stationCodes[code]
            station.set('location', str(getPosition(station)))
            objects = [ station ]
        else:
            print("FAILED: Station Not found. Check your speeling ;-)")
    return objects

def getSectorObjects(code):
    if code in sectorNames:
        code = sectorNames[code].get('code')
    sectorObjects = { 'stations':[], 'ships':[], 'vaults': [], 'flotsam': [] }
    for station in allStations:
        if station.get('sector_code') == code:
            sectorObjects['stations'] += [station]
    for ship in allShips:
        if ship.get('sector_code') == code:
            sectorObjects['ships'] += [ship]
    for vault in dataVaults:
        if vault.get('sector_code') == code:
            sectorObjects['vaults'] += [vault]
    for floater in flotsam:
        if floater.get('sector_code') == code:
            sectorObjects['flotsam'] += [floater]
    return sectorObjects

def getProximity(obj):
    closest = None
    distance = 9999999
    infos = []
    if type(obj) is str:
        objects = getObjects(obj)
        if len(objects) > 1:
            print("WARNING: Duplicate code exists for: " + obj + ". We could be tracking the wrong object")
        obj = objects[0]
    sectorCode = obj.get('sector_code')
    sectorObjects = getSectorObjects(sectorCode)
    oLocation = getPosition(obj)
    for station in sectorObjects['stations']:
        owner = station.get('owner')
        if owner in ["khaak", "xenon"]:
            continue
        sLocation = getPosition(station)
        sdist = math.sqrt(math.pow(sLocation['x'] - oLocation['x'],2) + math.pow(sLocation['z'] - oLocation['z'],2) + math.pow(sLocation['y'] - oLocation['y'],2))
        if closest == None or sdist < distance:
            closest = station.get('code')
            distance = sdist
            infos = buildProximityInfo(oLocation, sLocation, closest, distance)
    if playerLocation.get('sector_code') == sectorCode:
        pLocation = getPosition(playerLocation)
        pdist = math.sqrt(math.pow(pLocation['x'] - oLocation['x'],2) + math.pow(pLocation['z'] - oLocation['z'],2) + math.pow(pLocation['y'] - oLocation['y'],2))
        infos += buildProximityInfo(oLocation, pLocation, "player", pdist)
    return infos

def updateStatsInfo(stats, owner, type, subtype=None):
    if owner in stats:
        if type in stats[owner]:
            stats[owner][type]['total'] += 1
        else:
            stats[owner][type] = { 'total': 1 }
    else:
        stats[owner] = { type: { 'total': 1 } }
    if subtype:
        if subtype in stats[owner][type]:
            stats[owner][type][subtype] += 1
        else:
            stats[owner][type][subtype] = 1

def distance_between(p1, p2):
    xd = p1['x'] - p2['x']
    yd = p1['y'] - p2['y']
    zd = p1['z'] - p2['z']
    return math.sqrt(xd * xd + yd * yd + zd * zd)

def build_navigation_graph():
    global path_cache
    station_offset = len(gates)
    graph = defaultdict(list)
    path_cache = {}
    # connect gates that share the same shcon (instant travel)
    for group in gate_groups.values():
        for i in group:
            for j in group:
                if i != j:
                    graph[i].append((j, 0.0))
    # connect gates within the same sector
    for idxs in sector_gates.values():
        for a in range(len(idxs)):
            for b in range(a + 1, len(idxs)):
                d = distance_between(gates[idxs[a]]['pos'], gates[idxs[b]]['pos'])
                graph[idxs[a]].append((idxs[b], d))
                graph[idxs[b]].append((idxs[a], d))
    # connect stations to gates in their sector
    for si, station in enumerate(stations):
        node = station_offset + si
        for gidx in sector_gates.get(station['sector_code'], []):
            d = distance_between(station['pos'], gates[gidx]['pos'])
            graph[node].append((gidx, d))
            graph[gidx].append((node, d))
    return graph, station_offset

def shortest_path_distance(graph, start, goal, avoid_nodes=None):
    global path_cache, path_map_cache
    if avoid_nodes:
        # Run Dijkstra without caching when avoiding nodes
        dist_map = {start: 0.0}
        queue = [(0.0, start)]
        while queue:
            dist, node = heapq.heappop(queue)
            if dist > dist_map.get(node, float('inf')):
                continue
            for nxt, w in graph.get(node, []):
                if nxt in avoid_nodes and nxt != goal:
                    continue
                nd = dist + w
                if nd < dist_map.get(nxt, float('inf')):
                    dist_map[nxt] = nd
                    heapq.heappush(queue, (nd, nxt))
        return dist_map.get(goal, float('inf'))

    key = (start, goal)
    if key in path_cache:
        return path_cache[key]

    if start in path_map_cache:
        dist = path_map_cache[start].get(goal, float('inf'))
        path_cache[key] = dist
        path_cache[(goal, start)] = dist
        return dist

    dist_map = {start: 0.0}
    queue = [(0.0, start)]
    while queue:
        dist, node = heapq.heappop(queue)
        if dist > dist_map.get(node, float('inf')):
            continue
        for nxt, w in graph.get(node, []):
            nd = dist + w
            if nd < dist_map.get(nxt, float('inf')):
                dist_map[nxt] = nd
                heapq.heappush(queue, (nd, nxt))
    path_map_cache[start] = dist_map
    dist = dist_map.get(goal, float('inf'))
    path_cache[key] = dist
    path_cache[(goal, start)] = dist
    return dist

def getProfitableTrades(limit=5, max_cargo=None, use_distance=False,
                        origin=None, cargo_limit=None, credits=None,
                        avoid_illegal=False, avoid_hostile=False):
    heap = []
    for ware, sellers in trade_sellers.items():
        buyers = trade_buyers.get(ware)
        if not buyers:
            continue
        for sell in sellers:
            for buy in buyers:
                is_illegal_trade = sell.get('illegal') or buy.get('illegal')
                if avoid_hostile and (sell['sector_code'] in hostile_sectors or buy['sector_code'] in hostile_sectors):
                    continue
                if avoid_illegal and is_illegal_trade:
                    if sell['sector_code'] in illegal_sectors or buy['sector_code'] in illegal_sectors:
                        continue
                if buy['price'] <= sell['price'] or sell['amount'] == 0 or buy['amount'] == 0:
                    continue
                qty = min(sell['amount'], buy['amount'])
                if max_cargo is not None:
                    qty = min(qty, max_cargo)
                if cargo_limit is not None:
                    qty = min(qty, cargo_limit)
                if credits is not None and sell['price'] > 0:
                    qty = min(qty, int(credits // sell['price']))
                if qty == 0:
                    continue
                profit_per = buy['price'] - sell['price']
                total = profit_per * qty
                avoid_nodes = set()
                if avoid_hostile:
                    avoid_nodes.update(hostile_nodes)
                if avoid_illegal and is_illegal_trade:
                    avoid_nodes.update(illegal_nodes)
                avoid_nodes.difference_update({station_offset + sell['index'], station_offset + buy['index']})
                if len(avoid_nodes) == 0:
                    avoid_nodes = None
                if use_distance or avoid_nodes is not None:
                    dist_sell_buy = shortest_path_distance(
                        nav_graph,
                        station_offset + sell['index'],
                        station_offset + buy['index'],
                        avoid_nodes
                    )
                    if not math.isfinite(dist_sell_buy):
                        continue
                    player_leg = distance_between(origin, sell['pos']) if origin is not None else 0.0
                    dist = dist_sell_buy + player_leg
                    score = total / (dist / 1000.0) if dist > 0 else total
                    key = score
                else:
                    dist_sell_buy = distance_between(sell['pos'], buy['pos'])
                    player_leg = distance_between(origin, sell['pos']) if origin is not None else 0.0
                    dist = dist_sell_buy + player_leg
                    score = total
                    key = score
                deal = {
                    'ware': ware,
                    'from': sell,
                    'to': buy,
                    'qty': qty,
                    'profit_per': profit_per,
                    'total': total,
                    'distance': dist,
                    'sell_buy_dist': dist_sell_buy,
                    'player_dist': player_leg,
                    'score': score
                }
                if len(heap) < limit:
                    heapq.heappush(heap, (key, deal))
                else:
                    if key > heap[0][0]:
                        heapq.heapreplace(heap, (key, deal))

    return [d for _, d in sorted(heap, key=lambda x: x[0], reverse=True)]

def buildProximityInfo(oLocation, sLocation, closest, distance):
    infos = []
    if closest == "player":
        infos = ["", "The player is: " + str(int(distance/1000)) + " km from the object"]
    else:
        infos = [ "The closest station is: " + closest + ", distance: " + str(int(distance/1000)) + " km" ]
    infos += [ "Location: " +  str(sLocation) ]

    xd = oLocation['x'] - sLocation['x']
    yd = oLocation['y'] - sLocation['y']
    zd = oLocation['z'] - sLocation['z']
    if oLocation['x'] > sLocation['x']:
        infos += [ "Target is " + str(int(abs(xd/1000))) + " km to the east (X Axis)" ]
    else:
        infos += [ "Target is " + str(int(abs(xd/1000))) + " km to the west (X Axis)" ]
    if oLocation['z'] > sLocation['z']:
        infos += [ "Target is " + str(int(abs(zd/1000))) + " km to the north (Z Axis)" ]
    else:
        infos += [ "Target is " + str(int(abs(zd/1000))) + " km to the south (Z Axis)" ]
    if oLocation['y'] > sLocation['y']: #+y up
        infos += [ "Target is " + str(int(abs(yd/1000))) + " km above (Y Axis)" ]
    else:
        infos += [ "Target is " + str(int(abs(yd/1000))) + " km below (Y Axis)" ]
    return infos

def getPP(code):
    search = allStations + allShips + dataVaults
    for resource in search:
        if resource.get('code') == code:
            return getParPos(resource)

def getParPos(obj, positions=None):
    if positions == None:
        positions = []
    position = {'x':0.0, 'y':0.0, 'z':0.0, 'pitch':0.0, 'roll':0.0, 'yaw':0.0}
    macro = obj.get('macro')
    if macro != None:
        if macro in sector_zone_offsets:
            for key in sector_zone_offsets[macro].keys():
                position[key] += sector_zone_offsets[macro][key]
    objpos = obj.find('./offset/position')
    if objpos != None:
        position['x'] += float(objpos.get('x')) if 'x' in objpos.attrib else 0.0
        position['y'] += float(objpos.get('y')) if 'y' in objpos.attrib else 0.0
        position['z'] += float(objpos.get('z')) if 'z' in objpos.attrib else 0.0
    objrot = obj.find('./offset/rotation')
    if objrot != None:
        position['pitch'] += float(objrot.get('pitch')) if 'pitch' in objrot.attrib else 0.0
        position['roll'] += float(objrot.get('roll')) if 'roll' in objrot.attrib else 0.0
        position['yaw'] += float(objrot.get('yaw')) if 'yaw' in objrot.attrib else 0.0
    positions += [ { 'code': obj.get('code'), 'macro': obj.get('macro'), 'pos': position } ] 
    if ('class') in obj.attrib and obj.get('class') == 'galaxy':
        position['x'] = int(position['x'])
        position['y'] = int(position['y'])
        position['z'] = int(position['z'])
        position['pitch'] = int(position['pitch'])
        position['roll'] = int(position['roll'])
        position['yaw'] = int(position['yaw'])
        return positions
    return getParPos( obj.getparent(), positions )

def getPosition(obj, position=None):
    if position == None:
        position = {'x':0.0, 'y':0.0, 'z':0.0, 'pitch':0.0, 'roll':0.0, 'yaw':0.0}
    
    macro = obj.get('macro')
    if macro != None:
        if macro in sector_zone_offsets:
            for key in sector_zone_offsets[macro].keys():
                position[key] += sector_zone_offsets[macro][key]
    objpos = obj.find('./offset/position')
    if objpos != None:
        position['x'] += float(objpos.get('x')) if 'x' in objpos.attrib else 0.0
        position['y'] += float(objpos.get('y')) if 'y' in objpos.attrib else 0.0
        position['z'] += float(objpos.get('z')) if 'z' in objpos.attrib else 0.0
    objrot = obj.find('./offset/rotation')
    if objrot != None:
        position['pitch'] += float(objrot.get('pitch')) if 'pitch' in objrot.attrib else 0.0
        position['roll'] += float(objrot.get('roll')) if 'roll' in objrot.attrib else 0.0
        position['yaw'] += float(objrot.get('yaw')) if 'yaw' in objrot.attrib else 0.0
    if ('class') in obj.attrib and obj.get('class') == 'galaxy':
        position['x'] = int(position['x'])
        position['y'] = int(position['y'])
        position['z'] = int(position['z'])
        position['pitch'] = int(position['pitch'])
        position['roll'] = int(position['roll'])
        position['yaw'] = int(position['yaw'])
        return position
    return getPosition( obj.getparent(), position )

def printLbDv(resources, title, level=1):
    for resource in resources:
        sectorName = resource.get('sector_name') if ( resource.get('sector_name') != None ) else ""
        known2Player = 'True' if resource.get('knownto') == 'player' else 'False'
        proximity = resource.get('proximity')
        if proximity != None:
            proximity = json.loads(proximity)
        wares = resource.findall(".//ware")
        blueprints = resource.findall(".//component[@class='collectableblueprints']")
        cwares = resource.findall(".//component[@class='collectablewares']")
        print("\n" + title + ": " + resource.get('code') + ", Known2Player: " + known2Player + 
              "\n  Sector: " + sectorName + " (" + resource.get('sector_code') + ")")
        if int(level) > 1 or proximity != None:
            print("  Location: " + resource.get('location') + "\n")
        if proximity:
            for info in proximity:
                print("            " + info )
        if int(level) > 2:
            print("  Wares:")
            for ware in wares:
                amount = ware.get('amount') if 'amount' in ware.attrib else '1'
                print("    " + ware.get('ware') + ": " + amount )
            for bp in blueprints:
                print("    Blueprint: " + bp.get('blueprints') )
            for cash in cwares:
                amount = cash.get('money')
                if amount:
                    print("    Credits: " + amount )
                else:
                    print("     Collectable Ware: " + cash.attrib )
        print("")

def printShip(ship, level=1):
    title = ship.get('class')
    if title.startswith('ship'):
        title = "Ship"
    elif title == "station":
        title = "Station"
    else:
        title = "Code"
    sectorName = ship.get('sector_name') if ( ship.get('sector_name') != None ) else ""
    shipName = ship.get('name') if ( ship.get('name') != None ) else ""
    shipState = ship.get('state') if ( ship.get('state') != None ) else "space-worthy"
    proximity = ship.get('proximity')
    if proximity != None:
        proximity = json.loads(proximity)
    print("\n" + title + ": " + ship.get('code') + ", Class: " + ship.get('class') + ", Name: " + shipName +
            "\n  Macro: " + ship.get('macro') + "\n  SpawnTime: " + ship.get('spawntime') + "\n  State: " + shipState +
            "\n  Sector: " + sectorName + " (" + ship.get('sector_code') + ")" +
            "\n  Owner: " + ship.get('owner'))
    if int(level) > 1 or proximity != None:
        print("  Location: " + ship.get('location') + "\n")
    if proximity:
        for info in proximity:
            print("            " + info )
    if int(level) >2:
        engines = ship.findall("./connections/connection/component[@class='engine']")
        shields = ship.findall("./connections/connection/component[@class='shieldgenerator']")
        weapons = ship.findall("./connections/connection/component[@class='weapon']")
        turrets = ship.findall("./connections/connection/component[@class='turret']")
        software = ship.find("./software")
        consumables = ship.findall(".//ammunition/available/item")
        if engines != None:
            print("  Engines:")
            for engine in engines:
                print("    " + engine.get('macro'))
        if shields != None:
            print("  Shields:")
            for shield in shields:
                print("    " + shield.get('macro'))
        if weapons != None:
            print("  Weapons:")
            for weapon in weapons:
                print("    " + weapon.get('macro'))
        if turrets != None:
            print("  Turrets:")
            for turret in turrets:
                print("    " + turret.get('macro'))
        if software != None:
            print("  Software:")
            for sw in software.get('wares').split(" "):
                print("    " + sw)
        if consumables != None:
            print("  Consumables:")
            for cons in consumables:
                print("    " + cons.get('macro') + ": " + cons.get('amount'))
    print("")

def printXML(code):
    print("<matches>")
    if type(code) is str: 
        for obj in getObjects(code):
            print(etree.tostring(obj, pretty_print=True).decode())
    else:
        print(etree.tostring(code, pretty_print=True).decode())
    print("</matches>")

def getDupes(code=None):
    dupes = []
    wanted = [ code ]
    if code == None:
        wanted = duplicates
    for dupeCode in wanted:
        for obj in allComponents:
            if obj.get('code') == dupeCode:
                obj.set('location', str(getPosition(obj)))
                dupes += [obj]
    return dupes

def dumpDupes(code=None):
    dupes = getDupes(code)
    for dupe in dupes:
        print(dupe.attrib)

def updateAll(proximity=False):
    updateOwnerless(proximity)
    updateLockboxes(proximity)
    updateDataVaults(proximity)
    updateErlkingVaults(proximity)

def updateOwnerless(proximity=False):
    for ship in freeShips:
        updateObject(ship, proximity)

def updateObject(obj, proximity=False):
        obj.set('location', json.dumps(getPosition(obj)))
        if proximity:
            obj.set('proximity', json.dumps(getProximity(obj)))

def printOwnerless():
    print("")
    print("Ownerless Ships")
    print("===============")
    for ship in freeShips:
        printShip(ship, args.info)

def updateLockboxes(proximity=False):
    for lb in lockboxes:
        updateObject(lb, proximity)

def printLockboxes():
    print("")
    print("Lock Boxes")
    print("===============")
    printLbDv(lockboxes, "Lockbox", args.info)

def updateDataVaults(proximity=False):
    for vault in dataVaults:
        updateObject(vault, proximity)

def updateErlkingVaults(proximity=False):
    for vault in erlkingVaults:
        updateObject(vault, proximity)

def printDataVaults():
    print("")
    print("Data Vaults")
    print("===============")
    printLbDv(dataVaults, "Vault", args.info)

def printErlkingVaults():
    print("")
    print("Erlking Vaults")
    print("===============")
    printLbDv(erlkingVaults, "Vault", args.info)

def setLevel(level):
    args.info = level

print("Processing XML...")
start = time.time()
sectors = root.findall(".//universe/component/connections/connection/component/connections/connection/component[@class='sector']")
for sector in sectors:
    sectorMacro = sector.get('macro')
    sectorId = sector.get('id')
    sectorCode = sector.get('code')
    sectorName = sector_macros[sectorMacro] if sectorMacro in sector_macros else ""
    sector.set('sector_name', sectorName)

    if sector.get('owner') in illegal_factions:
        illegal_sectors.add(sectorCode)
    if sector.get('owner') in hostile_factions:
        hostile_sectors.add(sectorCode)

    updateStatsInfo(stats, sector.get('owner'), "sectors")

    sectorCodes[sectorCode] = sector
    if sectorCode in allCodes:
        warnings += ["WARNING: Sector Shares code with another Object. Sector: " + sectorName + ", Code: " + sectorCode]
    allCodes[sectorCode] = sector
    sectorNames[sectorName] = sector

    # gather all zone components so we can detect jump gates/accelerators
    zones = sector.findall('.//component[@class="zone"]')
    for zone in zones:
        macro = zone.get('macro', '')
        if macro.endswith('gatezone_macro'):
            gate_pos = getPosition(zone)
            gates.append({'sector_code': sectorCode, 'pos': gate_pos, 'macro': macro})
            idx = len(gates) - 1
            sector_gates[sectorCode].append(idx)
            m = re.search(r'shcon(\d+)_gatezone_macro$', macro)
            if m:
                gate_groups[m.group(1)].append(idx)

    resources = sector.findall("./connections/connection/component/connections/connection/component")
    for resource in resources:

        connection = resource.getparent().get('connection')
        resource.set('sector_code', sectorCode)
        resource.set('sector_name', sectorName)

        allComponents += [resource]
        myCode = resource.get('code')

        if myCode != None:
            if myCode in allCodes:
                warnings += ["WARNING: Duplicate code found for: " + myCode]
                duplicates += [myCode]
                if connection == "stations" and myCode in stationCodes:
                    warnings += ["WARNING: WARNING: The duplicate is another STATION. Two or more stations have the same code: " + myCode]
                elif connection == "ships" and myCode in shipCodes:
                    warnings += ["WARNING: WARNING: Duplicate is another SHIP. Two or more ships have the same code: " + myCode]
            else:
                allCodes[myCode] = resource
        
        player = resource.findall(".//component[@class='player']")
        if player != None and len(player) > 0:
            playerLocation = resource
            storage = resource.find(".//component[@class='storage']")
            if storage is not None:
                if 'capacity' in storage.attrib:
                    try:
                        playerCargo = int(float(storage.get('capacity')))
                    except ValueError:
                        pass

        if connection == "stations":
            if (resource.get('state') == "wreck"):
                if args.wrecks is False:
                    continue
            if resource.get('macro') == "station_pla_headquarters_base_01_macro":
                phq = resource
                resource.set('location', str(getPosition(resource)))
            allStations += [resource]
            if myCode != None:
                stationCodes[myCode] = resource
            if resource.get('owner') == "khaak":
                if "weaponplatform" not in resource.get('macro'):
                    khaakStations += [ resource ]
            updateStatsInfo(stats, resource.get('owner'), "stations")
            station_pos = getPosition(resource)
            station_index = len(stations)
            stations.append({'code': myCode if myCode else '', 'sector_code': sectorCode, 'pos': station_pos})
            trades = resource.findall('.//trade/offers//trade')
            for t in trades:
                ware = t.get('ware')
                price = float(t.get('price', '0'))
                amount = int(t.get('amount', '0'))
                illegal = 'shady' in t.get('flags', '')
                info = {
                    'station': myCode if myCode else '',
                    'sector_name': sectorName,
                    'sector_code': sectorCode,
                    'price': price,
                    'amount': amount,
                    'pos': station_pos,
                    'index': station_index,
                    'illegal': illegal
                }
                if 'seller' in t.attrib:
                    trade_sellers.setdefault(ware, []).append(info)
                elif 'buyer' in t.attrib:
                    trade_buyers.setdefault(ware, []).append(info)
        elif connection == "ships":
            if (resource.get('state') == "wreck"):
                if args.wrecks is False:
                    continue
            if (resource.get('owner') == "ownerless"):
                freeShips += [resource]
            elif (resource.get('owner') == "xenon"):
                xenonShips += [resource]
            elif (resource.get('owner') == "khaak"):
                khaakShips += [resource]
            allShips += [resource]
            if myCode != None:
                shipCodes[myCode] = resource
            updateStatsInfo(stats, resource.get('owner'), "ships", resource.get('class'))
        elif connection == "objects":
            compClass = resource.get('class')
            if compClass == "datavault":
                dataVaults += [resource]
                if myCode != None:
                    vaultCodes[myCode] = resource
            else:
                if resource.get('macro').startswith("landmarks_erlking_vault"):
                    erlkingVaults += [resource]
                    if myCode != None:
                        vaultCodes[myCode] = resource
                else:
                    flotsam += [resource]
        elif connection == "lockboxes":
            lockboxes += [resource]
            if myCode != None:
                lockboxCodes[myCode] = resource
        else:
            if connection.startswith('connection_clustergate'):
                connection = 'connection_clustergates'
            if connection in ignoredConnections:
                ignoredConnections[connection] = ignoredConnections[connection] +1
            else:
                ignoredConnections[connection] = 1
print('Done. Time: %.2f\n' % (time.time() - start))

nav_graph, station_offset = build_navigation_graph()

if args.avoid_illegal_sectors:
    for gidx, gate in enumerate(gates):
        if gate['sector_code'] in illegal_sectors:
            illegal_nodes.add(gidx)
    for si, station in enumerate(stations):
        if station['sector_code'] in illegal_sectors:
            illegal_nodes.add(station_offset + si)

if args.avoid_hostile_sectors:
    for gidx, gate in enumerate(gates):
        if gate['sector_code'] in hostile_sectors:
            hostile_nodes.add(gidx)
    for si, station in enumerate(stations):
        if station['sector_code'] in hostile_sectors:
            hostile_nodes.add(station_offset + si)


if args.ownerless:
    updateOwnerless(args.proximity)
    printOwnerless()

if args.lockboxes:
    updateLockboxes(args.proximity)
    printLockboxes()
        
if args.datavaults:
    updateDataVaults(args.proximity)
    printDataVaults()

if args.erlking:
    updateErlkingVaults(args.proximity)
    printErlkingVaults()

if args.code:
    print("\nMatching Codes")
    print("===============")
    matching = getObjects(args.code)
    for match in matching:
        updateObject(match, args.proximity)
        printShip(match, args.info)

if args.xenon:
    print("\nXenon Locations")
    print("===============")
    for x in xenonShips:
        updateObject(x, args.proximity)
        printShip(x, args.info)

if args.khaak:
    print("\nKhaak Locations")
    print("===============")
    for k in khaakShips:
        updateObject(k, args.proximity)
        printShip(k, args.info)

if args.khaakstations:
    print("\nKhaak Station Locations")
    print("===============")
    for ks in khaakStations:
        updateObject(ks, args.proximity)
        printShip(ks, args.info)

if args.whereswally:
    print("\nPlayer Location")
    print("===============")
    updateObject(playerLocation, args.proximity)
    printShip(playerLocation, args.info)

if args.factions:
    print("\nFactions")
    print("===============")
    line = "Faction          Sectors   Stations   Ships |     XS     S     M     L     XL"
    print("-" * len(line))
    print(line)
    print("-" * len(line))
    lines = 0
    for faction in stats:
        lines += 1
        line = faction.capitalize() + (" " * (14 - len(faction)))
        for resource in ["sectors", "stations", "ships"]:
            if resource in stats[faction]:
                res = str(stats[faction][resource]['total'])
                line += (" " * (3 + len(resource) - len(res))) + res 
            else:
                line += (" " * (2 + len(resource))) + "-"
        line += " |"
        for ship in ["ship_xs", "ship_s", "ship_m", "ship_l", "ship_xl"]:
            sub = ship.split('_')[1]
            if "ships" in stats[faction] and ship in stats[faction]['ships']:
                res = str(stats[faction]['ships'][ship])
                line += (" " * (5 + len(sub) - len(res))) + res
            else:
                line += (" " * (4 + len(sub))) + "-"
        print(line)
        if lines %2 == 0:
            print("-" * len(line))

if args.trades is not None:
    trade_args = args.trades
    limit = 5
    max_cargo = None
    if len(trade_args) >= 1 and trade_args[0] != '':
        limit = int(trade_args[0])
    if len(trade_args) >= 2:
        max_cargo = int(trade_args[1])
    use_player = args.player
    print("\nProfitable Trades")
    print("=================")
    origin_pos = None
    cargo_limit = max_cargo
    credits = None
    use_distance = args.distance or use_player
    if use_player and playerLocation is not None:
        origin_pos = getPosition(playerLocation)
        if playerCargo is not None:
            cargo_limit = playerCargo if max_cargo is None else min(max_cargo, playerCargo)
        credits = playerMoney
    deals = getProfitableTrades(limit, max_cargo, use_distance, origin_pos, cargo_limit, credits, args.avoid_illegal_sectors, args.avoid_hostile_sectors)
    for d in deals:
        profit_unit = f"${d['profit_per']:,.0f}"
        total_profit = f"${d['total']:,.0f}"
        base = f"{d['ware']}: {d['from']['station']} ({d['from']['sector_name']}) -> {d['to']['station']} ({d['to']['sector_name']})"
        out = f"{base} | Qty {d['qty']} Profit/unit {profit_unit} Total {total_profit}"
        if use_player and 'player_dist' in d:
            path = (
                f"{playerLocation.get('code')} ({playerLocation.get('sector_name')}) "
                f"({int(d['player_dist']/1000)}km)-> {d['from']['station']} "
                f"({d['from']['sector_name']}) ({int(d['sell_buy_dist']/1000)}km)-> "
                f"{d['to']['station']} ({d['to']['sector_name']})"
            )
            out = f"{d['ware']}: {path} | Qty {d['qty']} Profit/unit {profit_unit} Total {total_profit}"
        if 'distance' in d:
            if math.isfinite(d['distance']):
                out += f" Dist {int(d['distance']/1000)}km"
                if args.distance or use_player:
                    out += f" Score {int(d['score'])}"
            else:
                out += " Dist N/A"
        print(out)

if args.xml != None:
    printXML(args.xml)

if args.shell:
    print("")
    print("Python Shell starting...")
    print("")
    if not args.quiet:
        if len(warnings) > 0:
            for warning in warnings:
                print(warning)
            print("")
    print("Available Functions: \n")
    print("  getShips('code')          # Fetch information about a specific ship code (returns an array of ships)")
    print("  getStations('code')       # Fetch information about a specific station (returns an array of stations)")
    print("  getObjects('code')        # Fetch information about any object with a code (returns an array of objets)")
    print("  getSectors('code')        # Fetch information about a specific sector (returns an array of sectors)")
    print("  getSectorObjects('code')  # Fetch stations and ships currently inside the given sector")
    print("  printXML('code')          # Print the XML for a resource and its children")
    print("  getDupes('code')          # Fetch all duplicates or those with provided code")
    print("  dumpDupes('code')         # Print all duplicates or those with provided code")
    print("")
    print("Fetch interesting (special) resources")
    print("")
    print("  setLevel(int)                                          # Set information level for print functions")
    print("  update[Ownerless|LockBoxes|DataVaults|ErlkingVaults]() # Update locations for these objects")
    print("  print[Ownerless|LockBoxes|DataVaults|ErlkingVaults]()  # Print these objects information")
    print("  getProfitableTrades(n[, max_cargo, use_distance, origin, avoid_illegal, avoid_hostile])   # Return n most profitable trades")
    print("")
    print("  Eg. Display the ownerless ship locations:")
    print("")
    print("  >>> updateOwnerless()")
    print("  >>> printOwnerless()")
    print("")
    print("Or you know, just use python. The root of the xml tree is in var `root`. Other vars include:")
    print("lists:      sectors duplicates warnings allComponents allStations allShips freeShips")
    print("            xenonShips khaakShips dataVaults erlkingVaults lockboxes flotsam other")
    print("dicts:      sectorNames sectorCodes shipCodes stationCodes vaultCodes lockboxCodes allCodes")
    print("            ignoredConnections sector_zone_offsets sector_macros")
    print("")
    print("Examples")
    print("")
    print("  >>> print(json.dumps(dict(phq.attrib), indent=6)) ")
    print("  >>> printShip(getShips'ULC-584')[0],3)")
    print("")
    code.interact(local=locals())

