import csv
import sqlite3
import sys
import math
import json

def get_letter_tier(value):
    if value >= 9000:
        return 'P'
    if value >= 6500:
        return 'S+'
    if value >= 5000:
        return 'S'
    if value >= 4000:
        return 'A+'
    if value >= 3000:
        return 'A'
    if value >= 2000:
        return 'B+'
    if value >= 1000:
        return 'B'
    if value >= 500:
        return 'C'
    return 'D'

def get_qualifiers():
    cur = con.cursor()

    cur.execute('SELECT id, name, value FROM tournaments')

    tournaments = []
    for row in cur:
        blob = [row[0], row[1]]

        blob.append(get_letter_tier(row[2]))
        tournaments.append(blob)


    qualified = {}

    for tournament in tournaments:
        cutoff = 0
        if tournament[2] == 'SP':
            cutoff = 256
        elif tournament[2] == 'P+':
            cutoff = 192
        elif tournament[2] == 'P':
            cutoff = 128
        elif tournament[2] == 'S+':
            cutoff = 96
        elif tournament[2] == 'S':
            cutoff = 64
        elif tournament[2] == 'A+':
            cutoff = 48
        elif tournament[2] == 'A':
            cutoff = 32
        elif tournament[2] == 'B+':
            cutoff = 16
        elif tournament[2] == 'B':
            cutoff = 8
        elif tournament[2] == 'C':
            cutoff = 4
        elif tournament[2] == 'D':
            cutoff = 2

        cur.execute('SELECT place, player_id FROM placings WHERE tournament_id = ? AND place <= ?', (tournament[0], cutoff))

        for row in cur:
            if row[1] not in qualified:
                qualified[row[1]] = []

            qualified[row[1]].append((tournament[1], tournament[2], row[0]))

    with open('qualifiers.csv', newline='', mode='w') as csvfile:
        writer = csv.DictWriter(csvfile, ['id', 'player', 'qualified from'])
        writer.writeheader()

        for id_, data in qualified.items():
            cur.execute('SELECT tag FROM players WHERE id = ?', (id_, ))
            writer.writerow({'id': id_, 'player': cur.fetchone()[0], 'qualified from': ', '.join([str(datum) for datum in data])})


def get_event_winners():
    cur = con.cursor()

    winners = {}
    cur.execute('SELECT players.id, players.tag, tournaments.name FROM placings INNER JOIN players ON placings.player_id = players.id INNER JOIN tournaments ON placings.tournament_id = tournaments.id WHERE placings.place = 1')

    for row in cur:
        if row[0] not in winners:
            winners[row[0]] = {'tag': row[1], 'tournaments': []}
        winners[row[0]]['tournaments'].append(row[2])

    with open('winners.csv', mode='w', newline='') as winners_file:
        writer = csv.DictWriter(winners_file, ['id', 'player', '# wins', 'tournaments'])
        writer.writeheader()

        for id_, data in winners.items():
            writer.writerow({'id': id_, 'player': data['tag'], '# wins': len(data['tournaments']), 'tournaments': ', '.join(data['tournaments'])})

def get_common_h2hs():
    cur = con.cursor()

    h2hs = {}

    cur.execute('SELECT player_1_id, player_2_id, winner_id, player_1_score, player_2_score FROM sets')

    for row in cur:
        if row[3] == -1 or row[4] == -1:
            continue
        if row[2] != row[0] and row[2] != row[1]:
            continue

        if frozenset((row[0], row[1])) not in h2hs:
            h2hs[frozenset((row[0], row[1]))] = {row[0]: 0, row[1]: 0}
        h2hs[frozenset((row[0], row[1]))][row[2]] += 1

    with open('common_h2hs.csv', mode='w', newline='') as h2hs_file:
        writer = csv.DictWriter(h2hs_file, ['player 1 id', 'player 1 tag', 'player 1 score', 'player 2 id', 'player 2 tag', 'player 2 score', 'total'])
        writer.writeheader()

        h2hs_sorted = sorted(h2hs.items(), key=lambda set_counts:sum(set_counts[1].values()), reverse=True)

        tags = {}

        for h2h in h2hs_sorted:
            if sum(h2h[1].values()) < 2:
                break
            h2h_l = list(h2h[0])
            player_1 = h2h_l[0]
            player_2 = h2h_l[1]

            if player_1 not in tags:
                cur.execute('SELECT tag FROM players WHERE id = ?', (player_1, ))
                tags[player_1] = cur.fetchone()[0]
            if player_2 not in tags:
                cur.execute('SELECT tag FROM players WHERE id = ?', (player_2, ))
                tags[player_2] = cur.fetchone()[0]

            writer.writerow({'player 1 id': player_1, 'player 1 tag': tags[player_1], 'player 1 score': h2h[1][player_1],
                'player 2 id': player_2, 'player 2 tag': tags[player_2], 'player 2 score': h2h[1][player_2],
                'total': sum(h2h[1].values())})

def get_mu_chart(tournaments, player_ids):
    cur = con.cursor()

    player_id_set = set(player_ids)

    player_names = {}
    tournament_names = {}

    for player in player_ids:
        try:
            cur.execute('SELECT tag FROM players WHERE id = ?', (player, ))
            player_names[player] = cur.fetchone()[0]
        except:
            print(f'player {player} not found')
            sys.exit()

    for tournament in tournaments:
        try:
            cur.execute('SELECT name FROM tournaments WHERE id = ?', (tournament, ))
            tournament_names[tournament] = cur.fetchone()[0]
        except:
            print(f'key {tournament} not found')
            sys.exit()

    set_counts = {}
    for tournament in tournaments:
        print(f'reading {tournament}')
        cur.execute('SELECT player_1_id, player_2_id, winner_id, player_1_score, player_2_score, tournament_id FROM sets WHERE tournament_id = ?', (tournament, ))
        for row in cur:
            if row[3] == -1 or row[4] == -1:
                continue
            
            winner = row[2]
            loser = row[0] if row[1] == winner else row[1]
            winner_score = row[3] if winner == row[0] else row[4]
            loser_score = row[4] if winner == row[0] else row[3]

            if winner not in player_id_set and loser not in player_id_set:
                continue

            if (winner, loser) not in set_counts:
                set_counts[(winner, loser)] = []
            set_counts[(winner, loser)].append((row[5], winner_score, loser_score))

    print('read sets')

    for pair in set_counts.keys():
        if pair[0] not in player_names:
            cur.execute('SELECT tag FROM players WHERE id = ?', (pair[0], ))
            player_names[pair[0]] = cur.fetchone()[0]
        if pair[1] not in player_names:
            cur.execute('SELECT tag FROM players WHERE id = ?', (pair[1], ))
            player_names[pair[1]] = cur.fetchone()[0]

    with open('mu_chart.csv', newline='', mode='w') as chart_file, open('mu_details.txt', mode='w') as details_file:
        writer = csv.writer(chart_file)
        header_row = [player_names[id_] for id_ in player_ids]
        header_row.insert(0, '')
        header_row.append('Other losses')
        writer.writerow(header_row)

        for player_id in player_ids:
            row = []
            row.append(player_names[player_id])
            for other_id in player_ids:
                if other_id == player_id:
                    row.append('X')
                    continue
                row.append(f'{len(set_counts.get((player_id, other_id), []))} - {len(set_counts.get((other_id, player_id), []))}')
            losses = []
            for pair in set_counts.keys():
                if player_id != pair[1]:
                    continue
                if pair[0] in player_ids:
                    continue
                losses.append(f'{player_names[pair[0]]} ({len(set_counts.get((player_id, pair[0]), []))} - {len(set_counts.get((pair[0], player_id), []))})')
            row.append(' / '.join(losses))

            writer.writerow(row)

    print('fin')

def game_5():
    with open('game_5.csv', newline='', mode='w') as f:
        writer = csv.DictWriter(f, ['player', 'won', 'lost', 'ratio'])
        writer.writeheader()
        players = {}

        cur = con.cursor()
        cur.execute('SELECT player_1_id, player_2_id, winner_id, player_1_score, player_2_score FROM sets')

        ignore_scores = set([-1, 0, None, ''])

        for row in cur:
            win_score = row[3] if row[0] == row[2] else row[4]
            lose_score = row[4] if row[0] == row[2] else row[3]

            if win_score == 3 and lose_score == 2:
                win_id = row[2]
                lose_id = row[0] if row[1] == row[2] else row[1]
                if win_id not in players:
                    players[win_id] = [0,0] #w,l
                if lose_id not in players:
                    players[lose_id] = [0,0]
                players[win_id][0] += 1
                players[lose_id][1] += 1

        for k,v in players.items():
            ratio = v[0] / (v[0] + v[1]) if v[0] + v[1] != 0 else 0
            writer.writerow({'player': k, 'won': v[0], 'lost': v[1], 'ratio': ratio})


def get_tier_count(ignore_invitationals=False):
    with open('tier_count.csv', newline='', mode='w') as f:
        writer = csv.DictWriter(f, ['id', 'tag', 'P', 'S+', 'S', 'A+', 'A', 'B+', 'B', 'C', 'D', 'total'])
        writer.writeheader()

        cur = con.cursor()

        players = {}
        cur.execute('SELECT id, tag FROM players')
        for row in cur:
            players[row[0]] = {'id': row[0], 'tag': row[1], 'total': 0}

        query = 'SELECT placings.player_id, tournaments.value FROM placings INNER JOIN tournaments ON placings.tournament_id = tournaments.id WHERE placings.dq != 1'
        if ignore_invitationals:
            query += " AND tournaments.invitational = 0"

        cur.execute(query)

        for row in cur:
            letter_tier = get_letter_tier(row[1])
            if letter_tier not in players[row[0]]:
                players[row[0]][letter_tier] = 0
            players[row[0]][letter_tier] += 1
            players[row[0]]['total'] += 1

        for row in players.values():
            writer.writerow(row)


def get_regions():
    cur = con.cursor()

    players = {}
    cur.execute('SELECT id, tag FROM players')

    for row in cur:
        players[row[0]] = {'id': row[0], 'tag': row[1], 'region breakdown': {}, 'tournaments': [], 'tournament data': [], 'region': ''}

    cur.execute('SELECT placings.tournament_id, placings.player_id, tournaments.region, tournaments.name, placings.dq, tournaments.value, tournaments.id FROM placings INNER JOIN tournaments ON placings.tournament_id = tournaments.id WHERE placings.dq != 1')

    for row in cur:
        players[row[1]]['region breakdown'][row[2]] = players[row[1]]['region breakdown'].get(row[2], 0) + 1
        players[row[1]]['tournaments'].append(row[3])
        players[row[1]]['tournament data'].append((row[6], row[5], row[2])) # id value region


    for breakdown in players.values():
        if len(breakdown['tournaments']) == 0:
            breakdown['region'] = 'N/A'
            continue

        max_region = []
        max_region_count = 0

        for region, count in breakdown['region breakdown'].items():
            if count > max_region_count:
                max_region_count = count
                max_region = [region]
            elif count == max_region_count:
                max_region.append(region)

        if len(max_region) == 1:
            breakdown['region'] = max_region[0]
            continue

        small_region = set()
        small_region_value = 999999
        for tournament in breakdown['tournament data']:
            if tournament[2] not in max_region:
                continue
            if tournament[1] < small_region_value:
                small_region_value = tournament[1]
                small_region.clear()
                small_region.add(tournament[2])
            elif tournament[1] == small_region_value:
                small_region.add(tournament[2])

        breakdown['region'] = ' / '.join(small_region)

    filename = 'region_list.csv'

    with open(filename, mode='w', newline='') as csvfile:
        headers = ['id', 'tag', 'region', 'region breakdown', 'tournaments']

        writer = csv.DictWriter(csvfile, headers)
        writer.writeheader()

        iter_ = players.values()

        for p in iter_:
            p.pop('tournament data', None)

            p['region breakdown'] = json.dumps(p['region breakdown'])
            p['tournaments'] = json.dumps(p['tournaments'])

            writer.writerow(p)


def h2h_rank(n=100):
    rank = [['158026', 0]] # number 1 player is manual

    def get_best_stat(ranking, num, record_function):
        cur = con.cursor()

        players = ranking[:num]

        list_of_placeholders = ', '.join(['?'] * num)

        cur.execute(f'SELECT winner_id, player_1_id, player_2_id FROM sets WHERE (player_1_id IN ({list_of_placeholders}) OR player_2_id IN ({list_of_placeholders})) AND player_1_score != -1 AND player_2_score != -1', tuple(players + players))

        h2hs = {}
        for row in cur:
            if row[1] in players and row[2] in players:
                continue
            h2h_i = 2 if row[1] in players else 1

            if row[h2h_i] not in h2hs:
                h2hs[row[h2h_i]] = [0, 0]
            if row[0] in players:
                h2hs[row[h2h_i]][1] += 1
            else:
                h2hs[row[h2h_i]][0] += 1

        return sorted([[h2h, record_function(record, h2h)] for h2h, record in h2hs.items()], key=lambda val:val[1], reverse=True)

    losses_count = {}
    cur = con.cursor()
    cur.execute(f'SELECT winner_id, player_1_id, player_2_id FROM sets WHERE player_1_score != -1 AND player_2_score != -1')
    for row in cur:
        loser = row[1] if row[0] == row[2] else row[2]
        losses_count[loser] = losses_count.get(loser, 0) + 1

    cur.close()

    record_function = lambda record, h2h: record[0] / losses_count.get(h2h, 0.0001)

    while len(rank) < n:
        amount = len(rank)
        winrates = get_best_stat([record[0] for record in rank], amount, record_function)
        best_winrate = winrates[0][1]
        valid_players = [record for record in winrates if record[1] >= best_winrate]

        amount -= 1
        while len(valid_players) > 1 and amount > 0:
            winrates = get_best_stat([record[0] for record in rank], amount, record_function)
            winrate_dict = {}
            for winrate in winrates:
                if winrate[0] in [record[0] for record in valid_players]:
                    winrate_dict[winrate[0]] = winrate[1]
            if len(winrate_dict) == 0:
                amount -= 1
                continue
            best_winrate = max(winrate_dict.values())
            valid_players = [record for record in valid_players if record[0] in winrate_dict and winrate_dict[record[0]] == best_winrate]
            amount -= 1

        for record in valid_players:
            record[1] /= 10
            record[1] += len(rank)

        rank.extend(valid_players)
        print(len(rank))


    with open('h2hrank.csv', mode='w', newline='') as csvfile:
        headers = ['place', 'id', 'tag', 'wins']
        writer = csv.DictWriter(csvfile, headers)
        writer.writeheader()
        cur = con.cursor()
        for record in rank:
            cur.execute('SELECT tag FROM players WHERE id = ?', (record[0], ))

            win_percent, place = math.modf(record[1])
            win_percent *= 1000
            win_percent = round(win_percent, 3)

            place = int(place) + 1

            writer.writerow({'place': place, 'id': record[0], 'tag': cur.fetchone()[0], 'wins': win_percent})

def alexrank(original_file):
    ranks = {}
    with open(original_file) as f:
        i = 1
        for line in f:
            ranks[line.strip()] = i
            i += 1

    cur = con.cursor()

    tournaments = []
    cur.execute('SELECT id, name, date FROM tournaments ORDER BY date ASC')
    for row in cur:
        tournaments.append(row)

    for tournament_id, tournament_name, date in tournaments:
        updates = []

        cur.execute('SELECT winner_id, player_1_id, player_2_id, player_1_score, player_2_score FROM sets WHERE tournament_id = ? ORDER BY set_order ASC', (tournament_id, ))
        for row in cur:
            if row[3] == -1 or row[4] == -1:
                continue
            winner_id = row[0]
            loser_id = row[1] if winner_id == row[2] else row[2]
            if loser_id not in ranks:
                continue

            # ranks[loser_id] exists
            if winner_id in ranks:
                # switch
                if ranks[winner_id] > ranks[loser_id]:
                    higher_rank = ranks[loser_id]
                    lower_rank = ranks[winner_id]
                    ranks[winner_id] = higher_rank
                    ranks[loser_id] = lower_rank
                    updates.append([winner_id, loser_id, higher_rank, lower_rank])
            else:
                rank = ranks[loser_id]
                ranks[winner_id] = rank
                ranks.pop(loser_id)
                updates.append([winner_id, loser_id, rank])

        # output update
        if len(updates) == 0:
            continue
        print(f'Updates for {tournament_name} ({date})')
        for update in updates:
            cur.execute('SELECT tag FROM players WHERE id = ?', (update[0], ))
            winner = cur.fetchone()[0]
            cur.execute('SELECT tag FROM players WHERE id = ?', (update[1], ))
            loser = cur.fetchone()[0]
            if len(update) == 3:
                print(f'    {winner} ({update[0]}) > {loser} ({update[1]}) (takes #{update[2]})')
            elif len(update) == 4:
                print(f'    {winner} ({update[0]}) > {loser} ({update[1]}) (swaps #{update[2]} from #{update[3]})')

    final_rank = list(ranks.items())
    final_rank.sort(key=lambda x: x[1])
    for player_id, rank in final_rank:
        cur.execute('SELECT tag FROM players WHERE id = ?', (player_id, ))
        row = cur.fetchone()
        if row is None:
            tag = ''
        else:
            tag = row[0]
        print(f'#{rank}: {tag} ({player_id})')


def get_dqs():
    cur = con.cursor()

    dq_info = {}
    cur.execute('SELECT tournament_id, dq, count() FROM placings GROUP BY tournament_id, dq')

    for row in cur:
        if row[0] not in dq_info:
            dq_info[row[0]] = {'dq': 0, 'no_dq': 0}

        if row[1] == 1:
            dq_info[row[0]]['dq'] += row[2]
        else:
            dq_info[row[0]]['no_dq'] += row[2]

    with open('dqs.csv', mode='w', newline='') as dq_file:
        writer = csv.DictWriter(dq_file, ['tournament', 'dqs', 'total'])
        writer.writeheader()

        for tournament_id, info in dq_info.items():
            writer.writerow({'tournament': tournament_id, 'dqs': info['dq'], 'total': info['dq'] + info['no_dq']})


con = sqlite3.connect('ur_db_2025.db')

if __name__ == '__main__':
    get_tier_count()
