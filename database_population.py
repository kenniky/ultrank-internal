import csv
import sqlite3
import sys
import re
import json
import math
import uuid
from retrieve_startgg import get_placements, get_sets, collect_phases, strip_phase_ids, get_set, get_sets_from_phase_groups, collect_phase_groups
from startgg_toolkit import isolate_slug
from retrieve_challonge import get_challonge_data_with_id_to_id_match
from set_order import get_tournament_set_order_startgg, get_tournament_set_order_challonge, get_tournament_set_order_from_ids


def get_merge_player(id_):
    """Finds the final id that the given id merges to."""
    to_id = merges.get(id_, id_)

    if to_id == id_:
        return id_

    found_ids = set()

    while True:
        if to_id not in merges:
            return to_id 

        if to_id in found_ids:
            print(f'circle found {id_}')
            return (to_id)

        found_ids.add(to_id)
        to_id = merges[to_id]


def update_player_tags(players_blob):
    """Update player tags in bulk. Blob is generally a list of tuples."""
    for id_, tag in players_blob:
        update_player_tag(id_, tag)

def update_player_tag(id_, tag):
    """Updates the main tag of a given player.
    The previous tag is preserved in the other_tags field."""
    cur = con.cursor()

    cur.execute('SELECT * FROM players WHERE id = ?', (id_, ))

    row = cur.fetchone()

    if row is None:
        cur.execute('INSERT INTO players(id, tag, other_tags) VALUES(?, ?, ?)', (id_, tag, json.dumps([tag])))
    else:
        if row[1] != tag:
            past_tags = json.loads(row[2])

            if tag not in past_tags:
                past_tags.append(tag)

            cur.execute('UPDATE players SET tag = ?, other_tags = ? WHERE id = ?', (tag, json.dumps(past_tags), id_))

    con.commit()
    cur.close()

def add_alt_tags(players_blob):
    """Add alt tags in bulk. Blob is generally a list of tuples containing the id and the tag(s) to replace.
    sample blob: [(id1, tag1), (id2, [tag2_1, tag2_2])]"""
    for id_, tags in players_blob:
        if type(tags) == list:
            for tag in tags:
                add_alt_tag(id_, tag)
        else:
            update_player_tag(id_, tag)

def add_alt_tag(id_, tag):
    """Add an alternate tag for a player. This is simply added to their other_tags field
    and does not modify the main tag."""
    cur = con.cursor()

    cur.execute('SELECT * FROM players WHERE id = ?', (id_, ))

    row = cur.fetchone()

    if row is None:
        cur.execute('INSERT INTO players(id, tag, other_tags) VALUES(?, ?, ?)', (id_, tag, json.dumps([tag])))
    else:
        if row[1] != tag:
            past_tags = json.loads(row[2])

            if tag not in past_tags:
                past_tags.append(tag)

            cur.execute('UPDATE players SET other_tags = ? WHERE id = ?', (json.dumps(past_tags), id_))

    con.commit()
    cur.close()

def update_tournament_key(old_key, new_key):
    """Change the key for a given tournament."""
    cur = con.cursor()

    cur.execute('UPDATE tournaments SET id = ? WHERE id = ?', (new_key, old_key))
    cur.execute('UPDATE placings SET tournament_id = ? WHERE tournament_id = ?', (new_key, old_key))
    cur.execute('UPDATE sets SET tournament_id = ? WHERE tournament_id = ?', (new_key, old_key))

    con.commit()
    cur.close()

def merge_records(f_id, t_id):
    """Fully merge everything from f_id to t_id, and sets up a redirect for automatic future merging.
    Fails if a given tournament has placings for both players already."""
    from_id = str(f_id)
    to_id = str(t_id)

    merges[from_id] = to_id

    cur = con.cursor()

    cur.execute('REPLACE INTO MERGES(from_id, to_id) VALUES(?, ?)', (from_id, to_id))

    cur.execute('SELECT * FROM players WHERE id = ?', (from_id, ))

    if cur.fetchone() is None:
        con.commit()
        cur.close()
        return


    cur.execute('SELECT * FROM players WHERE id = ?', (to_id, ))
    row = cur.fetchone()

    if row is None:
        cur.execute('SELECT tag FROM players WHERE id = ?', (from_id, ))

        tag = cur.fetchone()[0]

        update_player_tag(to_id, tag)
    else:
        cur.execute('SELECT other_tags FROM players WHERE id = ?', (from_id, ))

        from_tags = cur.fetchone()[0]
        to_tags = row[2]

        final_tags = list(set(json.loads(from_tags)).union(set(json.loads(to_tags))))

        cur.execute('UPDATE players SET other_tags = ? WHERE id = ?', (json.dumps(final_tags), to_id))

    cur.execute('UPDATE placings SET player_id = ? WHERE player_id = ?', (to_id, from_id))
    cur.execute('UPDATE sets SET player_1_id = ? WHERE player_1_id = ?', (to_id, from_id))
    cur.execute('UPDATE sets SET player_2_id = ? WHERE player_2_id = ?', (to_id, from_id))
    cur.execute('UPDATE sets SET winner_id = ? WHERE winner_id = ?', (to_id, from_id))

    cur.execute('DELETE FROM players WHERE id = ?', (from_id,))

    con.commit()
    cur.close()

def combine_without_merging(f_id, t_id):
    """Fully move everything from f_id to t_id, but will not merge future additions.
    Fails if a given tournament has placings for both players already."""
    from_id = str(f_id)
    to_id = str(t_id)

    merges[from_id] = to_id

    cur = con.cursor()

    cur.execute('SELECT * FROM players WHERE id = ?', (from_id, ))

    if cur.fetchone() is None:
        con.commit()
        cur.close()
        return


    cur.execute('SELECT * FROM players WHERE id = ?', (to_id, ))
    row = cur.fetchone()

    if row is None:
        cur.execute('SELECT tag FROM players WHERE id = ?', (from_id, ))

        tag = cur.fetchone()[0]

        update_player_tag(to_id, tag)
    else:
        cur.execute('SELECT other_tags FROM players WHERE id = ?', (from_id, ))

        from_tags = cur.fetchone()[0]
        to_tags = row[2]

        final_tags = list(set(json.loads(from_tags)).union(set(json.loads(to_tags))))

        cur.execute('UPDATE players SET other_tags = ? WHERE id = ?', (json.dumps(final_tags), to_id))

    cur.execute('UPDATE placings SET player_id = ? WHERE player_id = ?', (to_id, from_id))
    cur.execute('UPDATE sets SET player_1_id = ? WHERE player_1_id = ?', (to_id, from_id))
    cur.execute('UPDATE sets SET player_2_id = ? WHERE player_2_id = ?', (to_id, from_id))
    cur.execute('UPDATE sets SET winner_id = ? WHERE winner_id = ?', (to_id, from_id))

    con.commit()
    cur.close()

    remove_empty_players()

def move_tournament(from_id, to_id, tournament_id):
    """Transfer a player's full record in a given tournament to another player.
    This includes placings and set wins/losses."""
    cur = con.cursor()

    cur.execute('SELECT * FROM placings WHERE tournament_id = ? AND player_id = ?', (tournament_id, from_id))

    if cur.fetchone() is None:
        print('nothing to move')
        return

    cur.execute('SELECT * FROM players WHERE id = ?', (to_id, ))
    if cur.fetchone() == None:
        cur.execute('SELECT tag FROM players WHERE id = ?', (from_id, ))

        tag = cur.fetchone()[0]

        update_player_tag(to_id, tag)

    cur.execute('UPDATE placings SET player_id = ? WHERE tournament_id = ? AND player_id = ?', (to_id, tournament_id, from_id))
    cur.execute('UPDATE sets SET player_1_id = ? WHERE tournament_id = ? AND player_1_id = ?', (to_id, tournament_id, from_id))
    cur.execute('UPDATE sets SET player_2_id = ? WHERE tournament_id = ? AND player_2_id = ?', (to_id, tournament_id, from_id))
    cur.execute('UPDATE sets SET winner_id = ? WHERE tournament_id = ? AND winner_id = ?', (to_id, tournament_id, from_id))

    con.commit()
    cur.close()

def swap_tournaments(id_1, id_2, tournament_id):
    """Swaps two players' tournament records from the same tournament."""
    cur = con.cursor()

    cur.execute('SELECT * FROM placings WHERE tournament_id = ? AND player_id = ?', (tournament_id, id_1))

    if cur.fetchone() is None:
        print(f'{id_1} no data for {tournament_id}')
        return

    cur.execute('SELECT * FROM placings WHERE tournament_id = ? AND player_id = ?', (tournament_id, id_2))

    if cur.fetchone() is None:
        print(f'{id_2} no data for {tournament_id}')
        return

    dummy_id = str(uuid.uuid4())

    move_tournament(id_1, dummy_id, tournament_id)
    move_tournament(id_2, id_1, tournament_id)
    move_tournament(dummy_id, id_2, tournament_id)

    remove_empty_players()

def grab_challonge_data(slug, id_=None, id_map={}, players=True, placings=True, sets=True, offset=0):
    """Imports Challonge tournament.

    Parameters:
    slug: Challonge id. challonge.com/abcdef => abcdef, xyz.challonge.com/abcdef => xyz-abcdef
    id_: id to use in the ultrank database
    id_map: maps Challonge player ids to database player ids, generates a new one if not specified for that player
    players: updates players' tags with names in Challonge bracket
    placings: records/updates placings into database
    sets: records/updates sets into database
    offset: set order offset"""
    if id_ is None:
        id_ = slug 

    placements, sets_ = get_challonge_data_with_id_to_id_match(slug, id_map)

    players_data = []
    placements_data = []

    for placement in placements:
        players_data.append((get_merge_player(placement['id']), placement['tag']))
        placements_data.append((id_, get_merge_player(placement['id']), placement['placement']))

    sets_data = []

    for set_ in sets_:
        players_data.append((get_merge_player(set_['p1_id']), set_['p1_tag']))
        players_data.append((get_merge_player(set_['p2_id']), set_['p2_tag']))
        sets_data.append((set_['id'], id_, get_merge_player(set_['p1_id']), get_merge_player(set_['p2_id']), get_merge_player(set_['winner']), set_['p1_score'], set_['p2_score']))

    players_data = list(set(players_data))

    cur = con.cursor()

    if players:
        update_player_tags(players_data)
    if placings:
        cur.executemany('REPLACE INTO placings(tournament_id, player_id, place, dq) VALUES(?, ?, ?, 0)', placements_data)
    if sets:
        cur.executemany('REPLACE INTO sets(set_id, tournament_id, player_1_id, player_2_id, winner_id, player_1_score, player_2_score) VALUES(?, ?, ?, ?, ?, ?, ?)', sets_data)

    con.commit()
    cur.close()

    populate_set_order_challonge(id_, slug, offset=offset)

    determine_dq_placings(id_)

def grab_tournament_data(slug, id_=None, players=True, placings=True, sets=True, phase_groups=None, do_set_order=True, offset=0):
    """Imports startgg tournament.

    Parameters:
    slug: startgg id. start.gg/tournament/abcdef/event/xyz => tournament/abcdef/event/xyz
    id_: id to use in the ultrank database
    players: updates players' tags with current start.gg tag
    placings: records/updates placings into database
    sets: records/updates sets into database
    phase_groups: only grab sets from these specific phase groups
    do_set_order: set to False to disable set order logging (long and rather intensive process)
    offset: set order offset"""
    if id_ is None:
        id_ = slug

    if phase_groups is None:
        phase_groups = collect_phase_groups(slug)

    placements = get_placements(slug, merges=merges)
    sets_ = get_sets_from_phase_groups(phase_groups, merges=merges)

    players_data = []
    placements_data = []

    for placement in placements:
        players_data.append((get_merge_player(placement['id']), placement['tag']))
        placements_data.append((id_, get_merge_player(placement['id']), placement['placement']))

    sets_data = []

    for set_ in sets_:
        players_data.append((get_merge_player(set_['p1_id']), set_['p1_tag']))
        players_data.append((get_merge_player(set_['p2_id']), set_['p2_tag']))
        sets_data.append((set_['id'], id_, get_merge_player(set_['p1_id']), get_merge_player(set_['p2_id']), get_merge_player(set_['winner']), set_['p1_score'], set_['p2_score']))

    players_data = list(set(players_data))

    cur = con.cursor()

    if players:
        update_player_tags(players_data)
    if placings:
        cur.executemany('REPLACE INTO placings(tournament_id, player_id, place, dq) VALUES(?, ?, ?, 0)', placements_data)
    if sets:
        cur.executemany('REPLACE INTO sets(set_id, tournament_id, player_1_id, player_2_id, winner_id, player_1_score, player_2_score) VALUES(?, ?, ?, ?, ?, ?, ?)', sets_data)

    con.commit()
    cur.close()

    if do_set_order:
        populate_set_order_startgg(id_, slug, offset=offset, phase_groups=phase_groups)

    determine_dq_placings(id_)

def grab_lcq_data(slug, id_, qualifiers, invitational_size, players=True, placings=True, sets=True, phases=None, set_order_offset=-3000):
    """Imports an LCQ to prepend onto an existing tournament.

    Parameters:
    slug: startgg id. start.gg/tournament/abcdef/event/xyz => tournament/abcdef/event/xyz
    id_: id of tournament in database, generally derived from the invitational event
    qualifiers: # of qualifiers, used to calibrate placings
    invitational_size: # of players in final invitational, used to calibrate placings
    players: updates players' tags with current start.gg tag
    placings: records/updates placings into database
    sets: records/updates sets into database
    phases: only grab sets from these specific phases
    set_order_offset: set order offset"""
    if id_ is None:
        id_ = slug

    if phases is None:
        phases = strip_phase_ids(collect_phases(slug))

    placements = get_placements(slug, merges=merges)
    sets_ = get_sets(slug, merges=merges, phases=phases)
    # print(sets_)

    players_data = []
    placements_data = []

    for placement in placements:
        players_data.append((get_merge_player(placement['id']), placement['tag']))

        if placement['placement'] > qualifiers:
            placements_data.append((id_, get_merge_player(placement['id']), placement['placement'] + invitational_size - qualifiers))

    sets_data = []

    for set_ in sets_:
        players_data.append((get_merge_player(set_['p1_id']), set_['p1_tag']))
        players_data.append((get_merge_player(set_['p2_id']), set_['p2_tag']))
        sets_data.append((set_['id'], id_, get_merge_player(set_['p1_id']), get_merge_player(set_['p2_id']), set_['winner'], set_['p1_score'], set_['p2_score']))

    players_data = list(set(players_data))

    cur = con.cursor()

    if players:
        update_player_tags(players_data)
    if placings:
        cur.executemany('REPLACE INTO placings(tournament_id, player_id, place, dq) VALUES(?, ?, ?, 0)', placements_data)
    if sets:
        cur.executemany('REPLACE INTO sets(set_id, tournament_id, player_1_id, player_2_id, winner_id, player_1_score, player_2_score) VALUES(?, ?, ?, ?, ?, ?, ?)', sets_data)

    con.commit()
    cur.close()

    populate_set_order_startgg(id_, slug, offset=set_order_offset, phases=phases)

    determine_dq_placings(id_, overwrite=True)

def get_merges():
    """Extracts all merges from the database"""
    merges = {}

    cur = con.cursor()

    cur.execute('SELECT from_id, to_id FROM merges')

    for row in cur:
        merges[row[0]] = row[1]

    return merges

def populate_merges():
    """Appends merges from merges.csv file to the database, applying merges where applicable.
    Rarely used."""
    with open('merges.csv', newline='') as mf:
        mr = csv.DictReader(mf)

        cur = con.cursor()

        merges = []
        for row in mr:
            merge_records(row['from'], row['to'])

def populate_tournament_keys():
    """Inserts tournament info into database from tournamentkeys.csv file. Does not populate placing/set data.
    Rarely used."""
    with open('tournamentkeys.csv', newline='') as tk:
        tr = csv.DictReader(tk)

        cur = con.cursor()

        data = []
        keys = set()
        repeat = 0
        for row in tr:
            key = row['smashdata key']

            if key == 'no smashdata key':
                key = '-'.join(filter(None, re.split(r'[^A-Za-z0-9_]+', row['Tournament'].lower())))

            while key in keys:
                key = key + '-' + str(repeat)
                repeat += 1

            data.append((key, row['Tournament'], int(row['Points']), row['Region'], row['Date'], row['Is Invitational?'] == 'TRUE'))
            keys.add(key)

        cur.executemany('INSERT INTO tournaments(id, name, value, region, date, invitational) VALUES (?, ?, ?, ?, ?, ?)', data)
        con.commit()

        cur.close()

def add_set(set_id, tournament_id=None, event_slugs=None):
    """Add a singular start.gg set to the database.

    Parameters:
    set_id: id of the start.gg set
    tournament_id: tournament to add the set to. Set to None to have tournament auto-inferred from the API
    event_slugs: skip if the set is not from one of these events"""
    set_data = get_set(set_id)

    if event_slugs is not None:
        if set_data['event_slug'] not in event_slugs:
            print('set with id {} not from a valid event'.format(set_id))
            return

    t_id = set_data['event_slug'].replace('tournament/', '').replace('/event/', '/') if tournament_id is None else tournament_id

    cur = con.cursor()

    update_player_tag(get_merge_player(set_data['p1_id']), set_data['p1_tag'])
    update_player_tag(get_merge_player(set_data['p2_id']), set_data['p2_tag'])
    cur.execute('REPLACE INTO sets(set_id, tournament_id, player_1_id, player_2_id, winner_id, player_1_score, player_2_score) VALUES(?, ?, ?, ?, ?, ?, ?)',
        (set_data['id'], t_id, get_merge_player(set_data['p1_id']), get_merge_player(set_data['p2_id']), set_data['winner'], set_data['p1_score'], set_data['p2_score']))

    con.commit()


def add_sets(ranges, tournament_id=None, event_slugs=None):
    """Adds sets from given id ranges.

    Parameters:
    ranges: id ranges of the start.gg sets to check. Ranges are inclusive on both sides
    tournament_id: tournament to add the sets to. Set to None to have tournament auto-inferred from the API
    event_slugs: skip an id if the corresponding set is not from one of these events"""
    for range_ in ranges:
        for i in range(range_[0], range_[1] + 1):
            add_set(i, tournament_id, event_slugs)


def grab_from_smashdata(slug, players=True, placings=True, sets=True):
    """Imports a tournament directly from the smashdata database.
    Obsolete."""
    con_smashdata = sqlite3.connect('../smashdata/ultimate_player_database/ultimate_player_database.db')
    cur_smashdata = con_smashdata.cursor()

    cur_smashdata.execute('SELECT placings from tournament_info where key = ?', (slug, ))

    placings = [(str(placing[0]), placing[1]) for placing in json.loads(cur_smashdata.fetchone()[0])]

    cur = con.cursor()

    if players:
        # populate players
        for placing in placings:
            id_ = placing[0]
            cur_smashdata.execute('SELECT tag FROM players WHERE player_id = ?', (id_, ))

            tag = cur_smashdata.fetchone()[0]

            update_player_tag(get_merge_player(id_), tag)

    if placings:
        # populate placings
        for placing in placings:
            cur.execute('REPLACE INTO placings(tournament_id, player_id, place, dq) VALUES(?, ?, ?, 0)', (slug, get_merge_player(placing[0]), placing[1]))

    if sets:
        # populate sets
        cur_smashdata.execute('SELECT key, p1_id, p2_id, winner_id, p1_score, p2_score FROM sets WHERE tournament_key = ?', (slug, ))

        for row in cur_smashdata:
            id_ = row[0].replace('gg__', '')

            p1_id = get_merge_player(str(row[1]))
            p2_id = get_merge_player(str(row[2]))
            w_id = get_merge_player(str(row[3]))

            cur.execute('REPLACE INTO sets(set_id, tournament_id, player_1_id, player_2_id, winner_id, player_1_score, player_2_score) VALUES(?, ?, ?, ?, ?, ?, ?)', (id_, slug, p1_id, p2_id, w_id, row[4], row[5]))
    con.commit()

    determine_dq_placings(slug)

def add_tournament(name, id_, value, region, date, invitational=False, phase_groups=None, do_set_order=True):
    """Adds tournament info to the database.
    If id_ contains a "/", attempts to grab the correponding tournament from start.gg.
        id_ = abc/xyz => grabs start.gg/tournament/abc/event/xyz
    """
    cur = con.cursor()

    new_id = id_

    if '/' not in id_:
        new_id = '-'.join(re.split(r'\W+', name.lower()))

    cur.execute('REPLACE INTO tournaments(id, name, value, region, date, invitational) VALUES (?, ?, ?, ?, ?, ?)', (new_id, name, value, region, date, 1 if invitational else 0))

    con.commit()
    cur.close()

    if '/' in id_:
        grab_tournament_data('tournament/' + id_.replace('/', '/event/'), id_, phase_groups=phase_groups, do_set_order=do_set_order)

def check_tournaments():
    """Outputs a csv file detailing number of players/sets in each event.
    Used for data validation purposes.
    """
    cur = con.cursor()

    tournament_data = {}
    cur.execute('SELECT id FROM tournaments')

    for row in cur:
        tournament_data[row[0]] = {'placings': 0, 'sets': 0}

    cur.execute('SELECT tournament_id FROM placings')

    for row in cur:
        tournament_data[row[0]]['placings'] += 1

    cur.execute('SELECT tournament_id FROM sets')

    for row in cur:
        tournament_data[row[0]]['sets'] += 1

    with open('db_summary.csv', newline='', mode='w') as summ_file:
        w = csv.DictWriter(summ_file, fieldnames=['tournament', 'placings', 'sets'])
        w.writeheader()

        for id_, data in tournament_data.items():
            w.writerow({'tournament': id_, 'placings': data['placings'], 'sets': data['sets']})


def output_sets(id_, file='sets.csv'):
    """Outputs every set from a given tournament into a CSV file.
    Used for data validation purposes (determining missing sets, bad merges etc.).
    """
    with open(file, newline='', mode='w') as sets_file:
        w = csv.DictWriter(sets_file, fieldnames=['id', 'winner', 'wtag', 'wscore', 'loser', 'ltag', 'lscore'])
        w.writeheader()

        cur = con.cursor()

        cur.execute('SELECT set_id, player_1_id, player_2_id, winner_id, player_1_score, player_2_score FROM sets WHERE tournament_id = ?', (id_, ))

        cur2 = con.cursor()

        tags = {}

        for row in cur:
            if row[3] != row[1] and row[3] != row[2]:
                w.writerow({'id': row[0]})
                continue

            winner = 1 if row[3] == row[1] else 2

            if row[1] not in tags:
                cur2.execute('SELECT tag FROM players WHERE id = ?', (row[1], ))
                tags[row[1]] = cur2.fetchone()[0]
            if row[2] not in tags:
                cur2.execute('SELECT tag FROM players WHERE id = ?', (row[2], ))
                tags[row[2]] = cur2.fetchone()[0]

            w.writerow({'id': row[0], 'winner': row[winner], 'wtag': tags[row[winner]], 'wscore': row[3 + winner], 'loser': row[3 - winner], 'ltag': tags[row[3 - winner]], 'lscore': row[6 - winner]})


def consolidate_merges():
    """Compresses merge chains so all merges refer to the final merge target. Also detects circular merge patterns."""
    global merges

    cur = con.cursor()

    for from_id, to_id in merges.items():
        actual_to_id = to_id
        found_ids = set()
        found_ids.add(from_id)

        while True:
            if actual_to_id in found_ids:
                break
            if actual_to_id not in merges:
                break 
            found_ids.add(actual_to_id)
            actual_to_id = merges[actual_to_id]
            print(actual_to_id)

        if actual_to_id in found_ids:
            print(f'discovered circle {from_id} -> {actual_to_id}')
        elif actual_to_id != to_id:
            print(f'updating {from_id}')
            cur.execute('UPDATE merges SET to_id = ? WHERE from_id = ?', (actual_to_id, from_id))

    cur.execute('DELETE FROM merges WHERE from_id = to_id')

    con.commit()
    cur.close()

    merges = get_merges()

def remove_tournament(id_, remove_players=True):
    """Fully removes a tournament from the database."""
    cur = con.cursor()

    cur.execute('DELETE FROM placings WHERE tournament_id = ?', (id_, ))
    cur.execute('DELETE FROM sets WHERE tournament_id = ?', (id_, ))
    cur.execute('DELETE FROM tournaments WHERE id = ?', (id_, ))

    con.commit()

    if remove_players:
        remove_empty_players()


def check_players(include_dqs=True, sort=False, stats=False):
    """Outputs a CSV with all players, regions attended, and tournaments attended.
    Primarily used to check for duplicate player entries.

    include_dqs: includes tournaments that the player fully DQd from
    sort: set to True to sort players by tag. Otherwise, players are ordered by database rowid, which is generally insertion order
    stats: output some counts alongside. Setting this to True automatically sets include_dqs to False 
    """
    cur = con.cursor()

    players = {}
    cur.execute('SELECT id, tag FROM players')

    for row in cur:
        players[row[0]] = {'id': row[0], 'tag': row[1], 'regions': {}, 'tournaments': [], 'num majors': 0}

    if include_dqs and not stats:
        cur.execute('SELECT placings.tournament_id, placings.player_id, tournaments.region, tournaments.name, placings.dq, tournaments.value FROM placings INNER JOIN tournaments ON placings.tournament_id = tournaments.id')
    else:
        cur.execute('SELECT placings.tournament_id, placings.player_id, tournaments.region, tournaments.name, placings.dq, tournaments.value FROM placings INNER JOIN tournaments ON placings.tournament_id = tournaments.id WHERE placings.dq != -1')

    for row in cur:
        players[row[1]]['regions'][row[2]] = players[row[1]]['regions'].get(row[2], 0) + 1
        players[row[1]]['tournaments'].append(row[3] if row[4] != 1 else (row[3], 'DQ'))
        if row[5] >= 3000:
            players[row[1]]['num majors'] += 1

    filename = 'player_check.csv'
    if sort:
        filename = 'player_check_sorted.csv'
    elif stats:
        filename = 'player_check_stats.csv'

    with open(filename, mode='w', newline='') as csvfile:
        headers = ['id', 'tag', 'regions', 'tournaments']
        if stats:
            headers.append('num regions')
            headers.append('num tournaments')
            headers.append('num majors')
        writer = csv.DictWriter(csvfile, headers)
        writer.writeheader()

        iter_ = players.values()
        if sort:
            iter_ = sorted(list(players.values()), key=lambda x: x['tag'].upper())

        for p in iter_:
            if stats:
                p['num regions'] = len(p['regions'])
                p['num tournaments'] = len(p['tournaments'])
            else:
                p.pop('num majors', None)

            p['regions'] = json.dumps(p['regions'])
            p['tournaments'] = json.dumps(p['tournaments'])

            writer.writerow(p)

def update_tournament_value(id_, value):
    """Updates point value of a given tournament."""
    cur = con.cursor()

    cur.execute('UPDATE tournaments SET value = ? WHERE id = ?', (value, id_))

    con.commit()

def determine_dq_placings(tournament_id=None, overwrite=False):
    """Updates a player's DQ status at a tournament.
    0 = did not DQ
    1 = full DQ, did not play any sets
    -1 = DQd but played some sets

    default behavior is to only check players with a current DQ status of 0.
    set overwrite to True to check all players, including players with a nonzero DQ status"""
    cur = con.cursor()

    if tournament_id is None:
        cur.execute('SELECT id FROM tournaments')
        tournaments = []
        for row in cur:
            tournaments.append(row[0])
    else:
        tournaments = [tournament_id]

    for tournament in tournaments:
        print(tournament)
        dqs = set()
        participated = set()

        cur.execute('SELECT player_1_id, player_2_id, player_1_score, player_2_score FROM sets WHERE tournament_id = ?', (tournament, ))

        for row in cur:
            if row[2] != -1 and row[3] != -1:
                participated.add(row[0])
                participated.add(row[1])
            else:
                if row[2] == -1:
                    dqs.add(row[0])
                if row[3] == -1:
                    dqs.add(row[1])

        # Full dqs (dq = 1): dqs - participated
        for player in dqs.difference(participated):
            cur.execute('UPDATE placings SET dq = 1 WHERE tournament_id = ? AND player_id = ?', (tournament, player))

        # Partial dqs (dq = -1): dqs ^ participated
        for player in dqs.intersection(participated):
            cur.execute('UPDATE placings SET dq = -1 WHERE tournament_id = ? AND player_id = ?', (tournament, player))


        # Not dq (dq = 0): participated - dqs
        if overwrite:
            for player in participated.difference(dqs):
                cur.execute('UPDATE placings SET dq = 0 WHERE tournament_id = ? AND player_id = ?', (tournament, player))

    con.commit()

def populate_loser_ids(overwrite=False):
    """Sets loser_ids of sets, inferred from winner_ids.
    Obsolete."""
    cur = con.cursor()
    cur.execute('SELECT set_id, winner_id, player_1_id, player_2_id, loser_id FROM sets')

    losers = []

    for row in cur:
        if row[1] is None:
            continue
        if not overwrite and row[4] is not None:
            continue

        if row[1] == row[2]:
            losers.append((row[3], row[0]))
        elif row[1] == row[3]:
            losers.append((row[2], row[0]))
        else:
            print(f'???? {row[0]}')

    cur.executemany('UPDATE sets SET loser_id = ? WHERE set_id = ?', losers)
    con.commit()


def remove_empty_players():
    """Removes player entries without associated placing or set data."""
    cur = con.cursor()

    players = set()

    cur.execute('SELECT player_id FROM placings')

    for row in cur:
        players.add(row[0])

    cur.execute('SELECT id FROM players')

    to_delete = set()

    for row in cur:
        if row[0] not in players:
            print(row[0])
            to_delete.add(row[0])
    
    for id_ in to_delete:
        cur.execute('DELETE FROM players WHERE id = ?', (id_, ))
        
    con.commit()

def get_tier(point_value):
    """Return letter tier of a given point value"""
    tiers = [(0, 500, 'D'), (500, 1000, 'C'), (1000, 2000, 'B'), (2000, 3000, 'B+'), (3000, 4000, 'A'), (4000, 5000, 'A+'), (5000, 6500, 'S'), (6500, 9000, 'S+'), (9000, 999999, 'P')]

    for tier in tiers:
        if point_value >= tier[0] and point_value < tier[1]:
            return tier[2]

    return 'X'

def get_placings(id_, filename='placings.csv'):
    """Export placings of a tournament to csv.
    Used to fix misconstructed brackets or unfinished Challonge tournaments."""
    cur = con.cursor()

    with open(filename, mode='w', newline='') as csvfile:
        writer = csv.DictWriter(csvfile, ['id', 'player', 'placing'])
        writer.writeheader()

        cur.execute('SELECT placings.player_id, players.tag, placings.place FROM placings INNER JOIN players ON placings.player_id = players.id WHERE placings.tournament_id = ?', (id_, ))

        for row in cur:
            writer.writerow({'id': row[0], 'player': row[1], 'placing': row[2]})

def update_placings(id_, filename='ch/placings - placings.csv'):
    """Import placings of a tournament from given csv file, overwriting whatever existed previously.
    You can exclude players to have their placings not overwritten.
    Uses same file structure as get_placings output"""
    cur = con.cursor()

    with open(filename, newline='') as csvfile:
        reader = csv.DictReader(csvfile)

        for row in reader:
            print(row)
            cur.execute('REPLACE INTO placings(place, tournament_id, player_id, dq) VALUES(?, ?, ?, 0)', (row['placing'], id_, row['id']))
        con.commit()

    determine_dq_placings(id_)


def populate_set_order_startgg(id_, slug, offset=0, phases=None, phase_groups=None):
    """Populates set order of a tournament from startgg.
    Note: set order is a partial order and is nondeterministic. The only guarantee is that a given set
    precedes any sets it directly feeds into (e.g. next round, losers' set, etc.)"""

    cur = con.cursor()

    set_order = get_tournament_set_order_startgg(slug, phases=phases, phase_groups=phase_groups)

    for i, set_id in enumerate(set_order):
        cur.execute('UPDATE sets SET set_order = ? WHERE set_id = ?', (i + offset, set_id))

    con.commit()
    print(id_)
    
def populate_set_order_startgg_from_ids(id_, slug, offset=0):
    """Populates set order of a tournament from startgg in a more API-intensive but reliable way,
    grabbing every set id first and then individually reading each set id."""
    cur = con.cursor()

    set_ids = []
    cur.execute('SELECT set_id FROM sets WHERE tournament_id = ?', (id_, ))
    for row in cur:
        set_ids.append(row[0])

    set_order = get_tournament_set_order_from_ids(set_ids)
    print(set_order)

    for i, set_id in enumerate(set_order):
        cur.execute('UPDATE sets SET set_order = ? WHERE set_id = ?', (i + offset, set_id))

    con.commit()
    print(id_)

def populate_set_order_challonge(id_, slug, offset=0):
    """Populates set order from challonge tournament."""
    cur = con.cursor()

    set_order = get_tournament_set_order_challonge(slug)

    for i, set_id in enumerate(set_order):
        cur.execute('UPDATE sets SET set_order = ? WHERE set_id = ?', (i + offset, set_id))

    con.commit()
    print(id_)


def get_player_summary(id_, include_ids=False, filename='player_summary.txt'):
    """output a txt file with a summary of the given player's full record in the database."""
    cur = con.cursor()

    with open(filename, mode='w') as summary_file:
        cur.execute('SELECT tag FROM players WHERE id = ?', (id_, ))

        summary_file.write(cur.fetchone()[0])
        if include_ids:
            summary_file.write(' - id {}'.format(id_))
        summary_file.write('\n\n')

        cur.execute('SELECT placings.tournament_id, placings.place, tournaments.name, tournaments.value, tournaments.date FROM placings INNER JOIN tournaments ON placings.tournament_id = tournaments.id WHERE placings.player_id = ? AND placings.dq != 1 ORDER BY tournaments.date', (id_, ))

        tournaments = []

        for row in cur:
            tournaments.append(tuple(row))

        for tournament in tournaments:
            tournament_id = tournament[0]
            summary_file.write('{} - {} - {} [{}]'.format(tournament[2], tournament[4], get_tier(tournament[3]), tournament[3]))
            if include_ids:
                summary_file.write(' ({})'.format(tournament_id))
            summary_file.write('\n')

            cur.execute('SELECT COUNT(*) FROM placings WHERE tournament_id = ?', (tournament_id, ))
            summary_file.write('Place {} / {}\n'.format(tournament[1], cur.fetchone()[0]))

            sets = []
            cur.execute('SELECT player_1_id, player_2_id, winner_id, player_1_score, player_2_score FROM sets WHERE tournament_id = ? AND (player_1_id = ? OR player_2_id = ?) ORDER BY set_id', (tournament_id, id_, id_))

            for row in cur:
                sets.append(tuple(row))

            for set_ in sets:
                result_string = '  W' if set_[2] == id_ else '  L'

                if set_[3] is None or set_[4] is None:
                    result_string += ' vs  '
                else:
                    if set_[3] == -1 or set_[4] == -1:
                        result_string += ' DQ  '
                    elif set_[0] == id_:
                        result_string += ' {}-{} '.format(set_[3], set_[4])
                    else:
                        result_string += ' {}-{} '.format(set_[4], set_[3])

                if set_[0] == id_:
                    cur.execute('SELECT tag FROM players WHERE id = ?', (set_[1], ))    
                else:
                    cur.execute('SELECT tag FROM players WHERE id = ?', (set_[0], ))
                
                result_string += cur.fetchone()[0]
                if include_ids:
                    result_string += ' ({})'.format(set_[1] if set_[0] == id_ else set_[0])
                result_string += '\n'
                
                summary_file.write(result_string)
            summary_file.write('\n')



def grab_tournament_file(id_, players_file, sets_file, set_id_prefix='', sets_uses_ids=False, players_headers=None, sets_headers=None):
    if players_headers is None:
        players_headers = {}
    if sets_headers is None:
        sets_headers = {}
    for player_header in ['place', 'tag', 'id']:
        if player_header not in players_headers:
            players_headers[player_header] = player_header
    for set_header in ['id', 'player1', 'player2', 'score1', 'score2']:
        if set_header not in sets_headers:
            sets_headers[set_header] = set_header

    players_data = []
    tags_dict = {}
    placements_data = []

    with open(players_file, newline='') as players_f:
        reader = csv.DictReader(players_f)

        for row in reader:
            player_id = get_merge_player(row[players_headers['id']])

            players_data.append((player_id, row[players_headers['tag']]))
            tags_dict[row[players_headers['tag']]] = player_id
            placements_data.append((id_, player_id, row[players_headers['place']]))

    sets_data = []

    with open(sets_file, newline='') as sets_f:
        reader = csv.DictReader(sets_f)

        for row in reader:
            p1_id = get_merge_player(row[sets_headers['player1']] if sets_uses_ids else tags_dict[row[sets_headers['player1']]])
            p2_id = get_merge_player(row[sets_headers['player2']] if sets_uses_ids else tags_dict[row[sets_headers['player2']]])
            score1 = row[sets_headers['score1']]
            score2 = row[sets_headers['score2']]

            winner_id = p1_id if score1 > score2 else p2_id if score2 > score1 else None

            sets_data.append((set_id_prefix + row[sets_headers['id']], id_, p1_id, p2_id, winner_id, score1, score2))

    cur = con.cursor()

    update_player_tags(players_data)
    cur.executemany('REPLACE INTO placings(tournament_id, player_id, place, dq) VALUES(?, ?, ?, 0)', placements_data)
    cur.executemany('REPLACE INTO sets(set_id, tournament_id, player_1_id, player_2_id, winner_id, player_1_score, player_2_score) VALUES(?, ?, ?, ?, ?, ?, ?)', sets_data)

    con.commit()
    cur.close()

    determine_dq_placings(id_)


def grab_challonge(slug, id_, use_placings=False, file_tags=False):
    with open(f'ch/ids - {slug}.csv', newline='') as csvfile:
        reader = csv.DictReader(csvfile)
        id_map = {}
        
        for row in reader:
            id_map[row['challonge_id']] = row['id']

        grab_challonge_data(slug, id_, id_map=id_map)

    if file_tags:
        with open(f'ch/ids - {slug}.csv', newline='') as csvfile:
            reader = csv.DictReader(csvfile)

            for row in reader:
                update_player_tag(row['id'], row['tag'])
    
    if use_placings:
        with open(f'ch/ids - {slug}.csv', newline='') as csvfile:
            cur = con.cursor()
            
            reader = csv.DictReader(csvfile)
            for row in reader:
                cur.execute('REPLACE INTO placings(tournament_id, player_id, place, dq) VALUES(?, ?, ?, 0)', (id_, get_merge_player(row['id']), row['placement']))

            determine_dq_placings(id_)

def validate_placings(tournament_id=None, auto_fix=False, verbose=False, ignore=[]):
    cur = con.cursor()
    if tournament_id is None:
        cur.execute('SELECT id FROM tournaments')
        tournaments = []
        for row in cur:
            if row[0] not in ignore_ids:
                tournaments.append(row[0])
    else:
        tournaments = [tournament_id]
    

    for tournament in tournaments:
        placings = []
        cur.execute('SELECT player_id, place FROM placings WHERE tournament_id = ?', (tournament, ))
        for row in cur:
            placings.append(row)

        placings.sort(key=lambda x: x[1])

        # check that placings match up
        placings_above = 0
        bad_placings = False

        for i in range(len(placings)):
            if i > 0 and placings[i][1] != placings[i-1][1]:
                placings_above = i

            if placings[i][1] != placings_above + 1:
                print(f'!!! {tournament} has placings that do not line up!')
                bad_placings = True
                break

        if bad_placings and auto_fix is not False:
            # fix the placings
            p_dict = {}
            for placing in placings:
                p_dict[placing[1]] = p_dict.get(placing[1], 0) + 1

            for u_placing in p_dict:
                new_placing = sum([pair[1] for pair in p_dict.items() if pair[0] < u_placing]) + 1
                if auto_fix == 'dryrun':
                    print(f'    {u_placing} -> {new_placing}')
                else:
                    cur.execute('UPDATE placings SET place = ? WHERE place = ? AND tournament_id = ?', (new_placing, u_placing, tournament))
                    con.commit()


        # check for very fine placings
        placings_trunc = [p[1] for p in placings]

        placings_uniq = set(placings_trunc)

        if len(placings_uniq) > 2 * math.log(len(placings_trunc), 2) + 2:
            print(f'!!! {tournament} has very fine placings - {len(placings_uniq)} / {len(placings_trunc)}')
            bad_placings = True

        if verbose and not bad_placings:
            print(f'{tournament} appears to have no issues')


    cur.close()


con = sqlite3.connect('ur_db_2026.db')
merges = get_merges()

if __name__ == '__main__':
    add_tournament("E-SPORTS \"GAME U\" FCPYS", 'e-sports-game-u-fcpys/ultimate-singles', 115, 'Central Mexico', '2026-04-27')

    # populate_set_order_startgg_from_ids('bayer-cup-grande-finale__ultimate-singles', 'tournament/bayer-cup-grande-finale/event/ultimate-singles')
    # tournaments = []

    # for row in cur:
    #     tournaments.append(row[0])

    # with open('datapopout.txt', mode='w') as write_file:
    #     for t in tournaments:
    #         if '__' not in t:
    #             print('not startgg: {}'.format(t), file=write_file)
    #             continue
    #         slug = 'tournament/' + t.replace('__', '/event/')
    #         try:
    #             grab_tournament_data(slug, t)
    #         except:
    #             print('catastrophic issue with {}'.format(t), file=write_file)
