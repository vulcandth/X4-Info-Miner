#!/usr/bin/env python3

from lxml import etree
import gzip
import sys
import argparse
import code
import json
import re
import time

parser = argparse.ArgumentParser()
parser.add_argument("savefile", help="The savegame you want to analyse")
parser.add_argument("-o", "--ownerless", help="Display ownerless ship locations", action="store_true")
parser.add_argument("-l", "--lockboxes", help="Display lockbox locations", action="store_true")
parser.add_argument("-d", "--datavaults", help="Display Data Vault locations", action="store_true")
parser.add_argument("-e", "--erlking", help="Display Erlking Data Vault locations", action="store_true")
parser.add_argument("-q", "--quiet", help="Suppress warnings in interactive mode", action="store_true")
parser.add_argument("-i", "--info", help="information level [1-3]. Default is 1 (sector only)", default='1')
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
dataVaults = []
erlkingVaults = []
lockboxes = []
flotsam = []
other = []
ignoredConnections = {}
sector_zone_offsets = {}
sector_macros = {}
phq = None

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

def getSector(code):
    if code in sectorCodes:
        return sectorCodes[code]
    elif code in sectorNames:
        return sectorNames[code]
    else:
        print("WARNING: Sector not found in map, full search will likely fail also")
        for sector in sectors:
            if sector.get('code') == code:
                return sector
        print("FAILED: Sector Not found. Check your speeling ;-)")

def getShip(code):
    if code in shipCodes:
        ship = shipCodes[code]
        ship.set('location', str(getPosition(ship)))
        return ship
    else:
        print("WARNING: Ship not found in map, full search will likely fail also")
        for ship in allShips:
            if ship.get('code') == code:
                ship.set('location', str(getPosition(ship)))
                return ship
        print("FAILED: Ship Not found. Check your speeling ;-)")
        
def getObject(code):
    if code in sectorCodes:
        return sectorCodes[code]
    elif code in sectorNames:
        return sectorNames[code]
    elif code in allCodes:
        if code in duplicates:
            print("WARNING: This object has known duplicates. The returned information could be inaccurate. Try getShip() or getStation() instead")
        obj = allCodes[code]
        obj.set('location', str(getPosition(obj)))
        return obj
    else:
        print("WARNING: object not found in any map, full search will likely fail also")
        for obj in allComponents:
            if obj.get('code') == code:
                obj.set('location', str(getPosition(obj)))
                return obj
        print("FAILED: object Not found. Check your speeling ;-)")

def getStation(code):
    if code in stationCodes:
        station = stationCodes[code]
        station.set('location', str(getPosition(station)))
        return station
    else:
        print("WARNING: Station not found in map, full search will likely fail also")
        for station in allStations:
            if station.get('code') == code:
                station.set('location', str(getPosition(station)))
                return station
        print("FAILED: Station Not found. Check your speeling ;-)")
        

def getSectorObjects(code):
    if code in sectorNames:
        code = sectorNames[code].get('code')
    sectorObjects = { 'stations':[], 'ships':[], 'vaults': [], 'flotsam': [] }
    for station in allStations:
        if station.get('sector_code') == code:
            sectorObjects['stations'] += [station]
    for ship in allShips:
        if ship.get('sector_code') == code:
            sectorObjects['ships'] += [station]
    for vault in dataVaults:
        if vault.get('sector_code') == code:
            sectorObjects['vaults'] += [vault]
    for floater in flotsam:
        if floater.get('sector_code') == code:
            sectorObjects['flotsam'] += [floater]
    return sectorObjects
            
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
        wares = resource.findall(".//ware")
        blueprints = resource.findall(".//component[@class='collectableblueprints']")
        cwares = resource.findall(".//component[@class='collectablewares']")
        print("\n" + title + ": " + resource.get('code') + ", Known2Player: " + known2Player + 
              "\n  Sector: " + sectorName + " (" + resource.get('sector_code') + ")")
        if int(level) > 1:
              print("  Location: " + resource.get('location') )
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
    sectorName = ship.get('sector_name') if ( ship.get('sector_name') != None ) else ""
    print("\nShip: " + ship.get('code') + ", Class: " + ship.get('class') + ", Macro: " + ship.get('macro') + 
            "\n  SpawnTime: " + ship.get('spawntime') + "\n  Sector: " + sectorName + " (" + ship.get('sector_code') + ")")
    if int(level) > 1:
        print("  Location: " + ship.get('location') + "\n")
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
    if type(code) is str: 
        print(etree.tostring(getObject(code), pretty_print=True).decode())
        if code in duplicates:
            print("WARNING: This object has known duplicates. The returned information could be inaccurate.")
    else:
        print(etree.tostring(code, pretty_print=True).decode())

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

def updateAll():
    updateOwnerless()
    updateLockboxes()
    updateDataVaults()
    updateErlkingVaults()

def updateOwnerless():
    for ship in freeShips:
        ship.set('location', str(getPosition(ship)))

def printOwnerless():
    print("")
    print("Ownerless Ships")
    print("===============")
    for ship in freeShips:
        printShip(ship, args.info)

def updateLockboxes():
    for lb in lockboxes:
        lb.set('location', str(getPosition(lb)))

def printLockboxes():
    print("")
    print("Lock Boxes")
    print("===============")
    printLbDv(lockboxes, "Lockbox", args.info)

def updateDataVaults():
    for vault in dataVaults:
        vault.set('location', str(getPosition(vault)))

def updateErlkingVaults():
    for vault in erlkingVaults:
        vault.set('location', str(getPosition(vault)))

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

    sectorCodes[sectorCode] = sector
    if sectorCode in allCodes:
        warnings += ["WARNING: Sector Shares code with another Object. Sector: " + sectorName + ", Code: " + sectorCode]
    allCodes[sectorCode] = sector
    sectorNames[sectorName] = sector

    zones = sector.findall(".//connections/connection/component[@class='zone']")

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
                if connection == "stations":
                    if myCode in stationCodes:
                        warnings += ["WARNING: WARNING: The duplicate is another STATION. Two or more stations have the same code: " + myCode]
                elif connection == "ships":
                    if myCode in shipCodes:
                        warnings += ["WARNING: WARNING: Duplicate is another SHIP. Two or more ships have the same code: " + myCode]
            else:
                allCodes[myCode] = resource
        
        if connection == "stations":
            if resource.get('macro') == "station_pla_headquarters_base_01_macro":
                phq = resource
                resource.set('location', str(getPosition(resource)))
            allStations += [resource]
            if myCode != None:
                stationCodes[myCode] = resource
        elif connection == "ships":
            if (resource.get('owner') == "ownerless"):
                freeShips += [resource]
            elif (resource.get('owner') == "xenon"):
                xenonShips += [resource]
            elif (resource.get('owner') == "khaak"):
                khaakShips += [resource]
            allShips += [resource]
            if myCode != None:
                shipCodes[myCode] = resource
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
print('Done. Time: %.2f' % (time.time() - start))


if args.ownerless:
    updateOwnerless()
    printOwnerless()

if args.lockboxes:
    updateLockboxes()
    printLockboxes()
        
if args.datavaults:
    updateDataVaults()
    printDataVaults()

if args.erlking:
    updateErlkingVaults()
    printErlkingVaults()

if args.shell:
    print("")
    print("Python Shell starting...")
    print("")
    if args.quiet == False:
        if len(warnings) > 0:
            for warning in warnings:
                print(warning)
            print("")
    print("Available Functions: \n")
    print("  getShip('code')           # Fetch information about a specific ship")
    print("  getStation('code')        # Fetch information about a specific station")
    print("  getObject('code')         # Fetch information about any object with a code")
    print("  getSector('code')         # Fetch information about a specific sector")
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
    print("  >>> printShip(getShip('ULC-584'),3)")
    print("")
    code.interact(local=locals())

