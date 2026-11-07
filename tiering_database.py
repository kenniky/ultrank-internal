import csv
import sqlite3
import json
import sys

MIDPOINT_DEPRECIATION = {
    300: 250,
    250: 200,
    200: 150,
    150: 100,
    100: 50,
    50: 30,
    30: 30,
    0: 0
}

class PlayerValue:
    def __init__(self, tag, id_, points, start_date, end_date):
        self.tag = tag
        self.id_ = id_ 
        self.points = points 
        self.start_date = start_date
        self.end_date = end_date

    def falls_in_date_range(self, date):
        after_start_date = self.start_date == '' or self.start_date is None or date >= self.start_date
        before_end_date = self.end_date == '' or self.end_date is None or date < self.end_date
        return after_start_date and before_end_date

    def __str__(self):
        return f'{self.tag} [{self.id_}] ({self.points} pts) / {self.start_date} - {self.end_date}'

def read_players():
    player_values = []
    invitational_values = []

    with open('../ultrank_invitational.csv', newline='', encoding='utf-8') as invit_file:
        reader = csv.DictReader(invit_file)

        for row in reader:
            id_ = replace_ids.get(row['Num'], row['Num'])
            if id_ == '':
                continue

            tag = row['Name'].strip()
            if tag == '':
                continue

            points = int(row['Additional Points'])

            start_date = row['Start Date']
            end_date = row['End Date']

            invitational_values.append(PlayerValue(tag, id_, points, start_date, end_date))


    with open('../ultrank_players.csv', newline='', encoding='utf-8') as players_file:
        reader = csv.DictReader(players_file)

        for row in reader:
            id_ = replace_ids.get(row['Start.gg Num ID'], row['Start.gg Num ID'])
            if id_ == '':
                continue

            tag = row['Player'].strip()
            if tag == '':
                continue

            if row['Points'] == '':
                points = 0
            else:
                points = int(row['Points'])

            start_date = row['Start Date']
            end_date = row['End Date']
            midpt_date = row['Midpt Date']

            if midpt_date == '':
                player_values.append(PlayerValue(tag, id_, points, start_date, end_date))
            else:
                player_values.append(PlayerValue(tag, id_, points, start_date, midpt_date))
                player_values.append(PlayerValue(tag, id_, MIDPOINT_DEPRECIATION[points], midpt_date, end_date))

    return player_values, invitational_values

def extract_tags(player_values):
    tags = {}

    for value in player_values:
        tags[value.id_] = value.tag

    return tags

def calculate_value(tournament_id):
    global overrides

    cur = con.cursor()

    cur.execute('SELECT region, date, invitational FROM tournaments WHERE id = ?', (tournament_id, ))
    row = cur.fetchone()

    if row[0] not in region_mults:
        print('missing region {}, assuming x3'.format(row[0]))
        region_mult = 3
    else:
        region_mult = region_mults[row[0]]
    date = row[1]
    is_invitational = row[2] == 1

    if not isinstance(region_mult, int):
        for timespan in region_mult:
            if (timespan[0] is None or date >= timespan[0]) and (timespan[1] is None or date < timespan[1]):
                region_mult = timespan[2]
                break

    cur.execute('SELECT COUNT(player_id) FROM placings WHERE tournament_id = ?', (tournament_id, ))

    num_entrants = cur.fetchone()[0]

    if tournament_id in entrant_overrides:
        num_entrants = entrant_overrides[tournament_id]

    cur.execute('SELECT player_id, dq FROM placings WHERE tournament_id = ?', (tournament_id, ))

    point_values = {}

    for row in cur:
        if row[1] == 1:
            # is a dq
            continue

        player_id = row[0]

        value = 0

        for player_value in player_values:
            if player_id != player_value.id_:
                continue
            if not player_value.falls_in_date_range(date):
                continue

            value = max(value, player_value.points)

        inv_value = 0

        if is_invitational:
            for invitational_value in invitational_values:
                if player_id != invitational_value.id_:
                    continue
                if not invitational_value.falls_in_date_range(date):
                    continue

                inv_value = max(inv_value, invitational_value.points)

        if value + inv_value == 0:
            continue

        if (tournament_id, player_id) in overrides:
            if overrides[(tournament_id, player_id)]:
                point_values[player_id] = value + inv_value
        else:
            if row[1] == -1:
                if (tournament_id, player_id) not in overrides:
                    decision = input('unsure on player {} ({}) at tournament {}, press 1 to ok: '.format(tags.get(player_id, player_id), player_id, tournament_id))

                    overrides[(tournament_id, player_id)] = decision.strip() == '1'

                    print('    (\'{}\', \'{}\'): {},'.format(tournament_id, player_id, 'True' if decision.strip() == '1' else 'False'))

                if overrides[(tournament_id, player_id)]:
                    point_values[player_id] = value + inv_value
            else:
                point_values[player_id] = value + inv_value


    if date < '2024-12-16':
        final_value = num_entrants * region_mult
    else:
        final_value = num_entrants
        if region_mult >= 2:
            final_value += min(num_entrants, 256)
        if region_mult >= 3:
            final_value += min(num_entrants, 128)
    values = []
    values.append(('entrants', final_value))

    for id_, value in point_values.items():
        final_value += value

        values.append((id_, tags.get(id_, ''), value))

    return {'id': tournament_id, 'value': final_value, 'date': date, 'values': json.dumps(values)}

def get_tier(point_value):
    for tier in tiers:
        if point_value >= tier[0] and point_value < tier[1]:
            return tier[2]
    return 'X'

def get_hb_start_date(date):
    for range_ in hb_ranges:
        if date >= range_[0] and date < range_[1]:
            return range_[0]

def get_hb_end_date(date):
    for range_ in hb_ranges:
        if date >= range_[0] and date < range_[1]:
            return range_[2]

region_mults = {
    'A.C.T.': [(None, '2023-07-24', 2), ('2023-07-24', None, 3)],
    'Alaska': 3,
    'Alberta': [(None, '2023-07-24', 2), ('2023-07-24', '2025-12-15', 3), ('2025-12-15', None, 2)],
    'Argentina': 3,
    'Arizona': 3,
    'Atlantic Canada': [(None, '2023-07-24', 2), ('2023-07-24', None, 3)],
    'Austria': [(None, '2024-12-16', 2), ('2024-12-16', None, 3)],
    'Baja California': [(None, '2023-07-24', 1), ('2023-07-24', '2025-12-15', 2), ('2025-12-15', None, 1)],
    'Bangalore': 3,
    'Barbados': 3,
    'Belgium': [(None, '2024-07-16', 2), ('2024-07-16', None, 3)],
    'Bolivia': 3,
    'British Columbia': [(None, '2026-07-13', 1), ('2026-07-13', None, 2)],
    'Carolinas': 2,
    'CenCal': 1,
    'Central Chile': 3,
    'Central France': 1,
    'Central Mexico': 1,
    'Central Spain': 2,
    'Central-West Brazil': 3,
    'Chile': 3,
    'China': 3,
    'Chubu': [(None, '2024-07-16', 2), ('2024-07-16', None, 1)],
    'Chugoku': [(None, '2023-07-24', 3), ('2023-07-24', None, 2)],
    'Colombia': 3,
    'Costa Rica': 3,
    'Cuba': 3,
    'Cyprus': 3,
    'Denmark': 3,
    'Dominican Republic': [(None, '2023-07-24', 3), ('2023-07-24', '2025-12-15', 2), ('2025-12-15', None, 3)],
    'East Mexico': [(None, '2023-07-24', 2), ('2023-07-24', None, 3)],
    'East Venezuela': 3,
    'Eastern China': 3,
    'Ecuador': 3,
    'El Salvador': [(None, '2026-07-13', 3), ('2026-07-13', None, 2)],
    'Finland': 3,
    'Florida': [(None, '2025-12-15', 1), ('2025-12-15', None, 2)],
    'France': 1,
    'French West Indies': 3,
    'Georgia': [(None, '2024-07-16', 1), ('2024-07-16', None, 2)],
    'Germany': 2,
    'Great Basin': [(None, '2024-12-16', 1), ('2024-12-16', None, 2)],
    'Great Britain': 2,
    'Great Lakes': 1,
    'Great Lakes East': 2,
    'Great Lakes West': [(None, '2024-12-16', 1), ('2024-12-16', None, 2)],
    'Greece': 3,
    'Guam': 3,
    'Guatemala': 3,
    'Hawaii': 3,
    'Heartland': [(None, '2023-07-24', 1), ('2023-07-24', None, 2)],
    'Heartland North': 3,
    'Heartland South': 2,
    'Hokkaido': [(None, '2023-07-24', 3), ('2023-07-24', '2026-07-13', 2), ('2026-07-13', None, 3)],
    'Hokuriku': 3,
    'Honduras': 3,
    'Hong Kong': 3,
    'Hungary': 3,
    'I/G Southeast': [(None, '2024-12-16', 2), ('2024-12-16', None, 3)],
    'Iceland': 3,
    'India': 3,
    'Indonesia': 3,
    'Ireland': 3,
    'Israel': 3,
    'Italy': [(None, '2024-07-16', 2), ('2024-07-16', None, 3)],
    'Kansai': 1,
    'Kanto': 1,
    'Kuwait': 3,
    'Kyushu': [(None, '2024-12-16', 1), ('2024-12-16', None, 2)],
    'Louisiana': 3,
    'Luxembourg': 3,
    'Madagascar': 3,
    'Malaysia': 3,
    'Manitoba': [(None, '2023-07-24', 2), ('2023-07-24', None, 3)],
    'Martinique': 3,
    'MD/VA': [(None, '2024-12-16', 1), ('2024-12-16', None, 2)],
    'Mid-South': [(None, '2023-07-24', 2), ('2023-07-24', None, 3)],
    'Morocco': 3,
    'N. Mariana Islands': 3,
    'Netherlands': [(None, '2023-07-24', 2), ('2023-07-24', '2024-07-16', 3), ('2024-07-16', '2024-12-16', 2), ('2024-12-16', None, 3)],
    'New Brunswick': 3,
    'New Caledonia': 3,
    'New England': [(None, '2023-07-24', 1), ('2023-07-24', None, 2)],
    'Newfoundland': 3,
    'New South Wales': [(None, '2024-12-16', 2), ('2024-12-16', None, 3)],
    'New Zealand': 3,
    'Nicaragua': 3,
    'NorCal': [(None, '2024-12-16', 1), ('2024-12-16', None, 3)],
    'North Brazil': 3,
    'North Chile': 3,
    'North Central Mexico': [(None, '2023-07-24', 2), ('2023-07-24', None, 3)],
    'North Germany': 2,
    'North Spain': 2,
    'Northeast Brazil': 3,
    'Northeast France': [(None, '2026-07-13', 1), ('2026-07-13', None, 2)],
    'Northeast Mexico': 2,
    'Northern Brazil': 3,
    'Northern China': 3,
    'Northern England': 2,
    'Northern Ontario': 3,
    'Northwest France': [(None, '2025-07-07', 1), ('2025-07-07', None, 2)],
    'Northwest Mexico': 2,
    'Northwest Mountains': 3,
    'Nova Scotia': 3,
    'Norway': 3,
    'Okinawa': 3,
    'Ontario': [(None, '2025-12-15', 1), ('2025-12-15', None, 2)],
    'Other India': 3,
    'Pacific Northwest': [(None, '2024-12-16', 1), ('2024-12-16', None, 2)],
    'Panama': 3,
    'Paraguay': 3,
    'Peru': 3,
    'Philippines': 3,
    'Poland': 3,
    'Portugal': 3,
    'Prince Edward Island': 3,
    'Puerto Rico': [(None, '2023-07-24', 3), ('2023-07-24', '2024-12-16', 2), ('2024-12-16', None, 3)],
    'Qatar': 3,
    'Quebec': [(None, '2023-07-24', 1), ('2023-07-24', '2024-12-16', 2), ('2024-12-16', None, 3)],
    'Quebec & Ottawa': 3,
    'Queensland': [(None, '2023-07-24', 2), ('2023-07-24', None, 3)],
    'Reunion': 3,
    'Rocky Mountains': 3,
    'Russia': 3,
    'Saskatchewan': [(None, '2023-07-24', 2), ('2023-07-24', None, 3)],
    'Saudi Arabia': 3,
    'Scotland': 3,
    'Serbia': 3,
    'Shikoku': 3,
    'Singapore': 3,
    'SoCal': [(None, '2024-12-16', 1), ('2024-12-16', None, 2)],
    'South Australia': [(None, '2024-12-16', 2), ('2024-12-16', None, 3)],
    'South Brazil': 3,
    'Southern France': 1,
    'South Germany': [(None, '2025-07-07', 2), ('2025-07-07', None, 3)],
    'South Mexico': 3,
    'South Korea': 3,
    'South Spain': [(None, '2026-07-13', 2), ('2026-07-13', None, 3)],
    'Southeast Brazil': 3,
    'Southern China': 3,
    'Southern England': 2,
    'Southwest': [(None, '2024-07-16', 1), ('2024-07-16', None, 3)],
    'Spain': 2,
    'Sweden': 3,
    'Switzerland': [(None, '2023-07-24', 2), ('2023-07-24', None, 3)],
    'Taiwan': 3,
    'Tasmania': 3,
    'Texas': [(None, '2025-12-15', 1), ('2025-12-15', '2026-07-13', 2), ('2026-07-13', None, 1)],
    'Texas / Louisiana': 1,
    'Thailand': 3,
    'Tohoku': 3,
    'Trinidad & Tobago': 3,
    'Trinidad and Tobago': 3,
    'Tristate': 1,
    'Turkey': 3,
    'U.A.E.': 3,
    'United Kingdom': [(None, '2023-07-24', 1), ('2023-07-24', None, 2)],
    'Upstate NY': [(None, '2023-07-24', 2), ('2023-07-24', None, 3)],
    'Uruguay': 3,
    'Venezuela': 3,
    'Victoria': [(None, '2024-12-16', 2), ('2024-12-16', None, 3)],
    'West Australia': [(None, '2023-07-24', 2), ('2023-07-24', None, 3)],
    'Western Australia': [(None, '2023-07-24', 2), ('2023-07-24', None, 3)],
    'West Germany': 2,
    'West Mexico': 2,
    'West Venezuela': 3,
    'Yucatan Peninsula': [(None, '2024-07-16', 2), ('2024-07-16', None, 3)],
}

replace_ids = {
    '1276498': '367317',
    '533753': '244649',
    '1215486': '1655772',
    '942022': '567585',
    '1233540': '1206833',
    '1238871': '2241260'
}

overrides = { # True = count still, False = don't count
    ('geekdom-22', '1928594'): False,
    ('movement-smash-100-100-pot-bonus__ultimate-singles', '1063610'): False,
    ('let-s-make-big-moves-2023__ultimate-singles', '231113'): False,
    ('72-8__road-to-top-monthly-tournament-s9e1', '1399419'): True,
    ('habby-birthday-2023-ft-1500-pot-bonus-an-abb-ontario__ultimate-singles', '2512815'): True,
    ('9-16__singles', '2315968'): True,
    ('keep-it-real-u-be-my-valentine-100-pot-bonus__ultimate-singles-100-pot-bonus', '18802'): False,
    ('keep-it-real-u-be-my-valentine-100-pot-bonus__ultimate-singles-100-pot-bonus', '71203'): True,
    ('st-albert-smash-13__ultimate-singles', '1006473'): False,
    ('cybersmash-2__smash-1v1', '129186'): False,
    ('spring-gatorlan-2023-1__super-smash-bros-ultimate', '24971'): False,
    ('ultimajac-4__ultimate-singles', '11154'): True,
    ('warlock-x-hex-the-hex-of-sorcerer-vol-vii__warlock-singles', '1720743'): True,
    ('front-runners-6__ultimate-singles', '276766'): True,
    ('ova-xxi-the-factory-2__ultimate-singles-4-00-pm', '69011'): True,
    ('the-come-up-2023-ft-amsa-aklo-tilde-gen-more__ultimate-singles', '2512815'): False,
    ('frismash-easter-cup__ultimate-singles', '273613'): True,
    ('delta-4__singles', '1309647'): True,
    ('buddwaur-s-birthday-bash-4-graduation-edition__ultimate-singles', '353073'): True,
    ('meteor-fest-2023__singles-meteor-fest', '271644'): True,
    ('momocon-2023__smash-ultimate-singles', '18802'): True,
    ('gateway-legends-2023-ft-10-000-pot-bonus__ultimate-singles-512-player-cap', '24971'): False,
    ('bron-esport-games__ultimate-singles', '2062749'): False,
    ('knockout-series-monthly-4-pre-bam__ultimate-singles', '523823'): True,
    ('no-style-invitational-2-000-prize-pot__ultimate-singles', '2512815'): False,
    ('tec-in-place-3__ultimate-singles-1v1', '546734'): False,
    ('reset-by-game-on__single', '241831'): True,
    ('reunion-2-2__singles', '2776736'): True,
    ('le-hub-mensuel-juin-2023-le-hub-monthly-june-2023__ultimate-singles-14h-2-pm', '68824'): True,
    ('84-1__road-to-top-monthly-tournament-s9e6', '2706128'): True,
    ('nova-bxl-summer-edition__smash-ultimate-1v1', '996707'): True,
    ('high-rez__smash-ultimate-singles-day-two', '249838'): True,
    ('smash-factor-x__smash-bros-ultimate-singles', '408055'): True,
    ('keep-it-real-summer-splash-500-pot-bonus__ultimate-singles', '1480393'): True,
    ('shweepless-in-seattle-a-cascadia-clash-tale__ultimate-singles', '1094952'): True,
    ('frismash-swiss-cup-2023__ultimate-singles', '50875'): True,
    ('let-s-make-big-moves-2023__ultimate-singles', '53621'): True,
    ('collision-2023-5__ultimate-singles', '30253'): True,
    ('regen-2023__ultimate-singles', '247423'): True,
    ('mensual-rel-mpago__ultimate-singles-3-30-pm', '937555'): True,
    ('40-sp-1__1on1', '1381404'): True,
    ('40-sp-1__1on1', '3179471'): True,
    ('cirque-du-cfl-1000-pot-bonus-cfl-regional__smash-ultimate-1v1', '1042374'): False,
    ('regen-2023__ultimate-singles', '889697'): False,
    ('top-14-maesumatop-14__singles-tournament', '2215215'): False,
    ('rva-smash-100-feat-100-pot-bonus-singles-100-pot__ultimate-singles', '1074811'): False,
    ('smash-connecturday-2023__torneo-1v1-s-bado', '129186'): True,
    ('tri-harder-melee__ultimate-singles', '240882'): True,
    ('fancon-smashxheaven-feat-sparg0__ultimate-singles-saturday-2pm', '61918'): True,
    ('pearl-two__ultimate-singles', '2274077'): True,
    ('smash-play-sorbonne-u-festival-2__1v1', '999527'): False,
    ('sp-22__1on1', '3179471'): True,
    ('kings-of-hali-6__ultimate-singles', '2376711'): True,
    ('hooters-universidad-smash-ultimate-7-00pm__hooters-ultimate-tournament-7-00-pm', '205133'): True,
    ('11-kagaribi-11__singles', '360589'): True,
    ('11-kagaribi-11__singles', '986202'): True,
    ('catamount-clash-4-a-link-to-the-mountains-200-pot__the-fight-for-hyrule-s-strongest-ultimate-singles', '1194511'): True,
    ('smash-legends-4__singles', '2205508'): True,
    ('batavia-brawl-halloween__smash-ultimate-singles', '1681123'): True,
    ('luminosity-makes-moves-miami-2023__ultimate-singles', '532139'): False,
    ('the-graveyard-2023__ultimate-singles', '68630'): True,
    ('couchwarriors-vic-november-ranking-battle-2023-smash-cwleague__smash-ultimate-singles', '1347288'): True,
    ('vca-vienna-challengers-arena-2023__super-smash-bros-ultimate-singles', '945363'): True,
    ('astral-finish-festival-2023__super-smash-bros-ultimate-switch', '2252178'): True,
    ('zoner-s-paradise-43__zoner-s-paradise-43', '419695'): True,
    ('top-15-final-maesumatop-15-final__singles-tournament', '569727'): True,
    ('ultimate-fighting-arena-2023__super-smash-bros-ultimate-single-1vs1', '151685'): True,
    ('port-priority-8-5__ultimate-singles', '249354'): True,
    ('tera__tera-singles', '877560'): True,
    ('hfil-monthly-12__ultimate-50-pot-bonus', '1807531'): True,
    ('ibero-reto-supremo-powered-by-ocm__ibero-reto-supremo', '961165'): True,
    ('snow-ball-smash-out-3__smash-ultimate-singles-bracket', '1099727'): False,
    ('brooklan-brawls-100__brooklan-brawls-100-smash-ultimate-singles', '4702'): False,
    ('failsafe-winter-2024-200-pot-bonus__ultimate-singles', '6301'): True,
    ('milano-smash-district-xix__singles', '669574'): True,
    ('megacon-2024__super-smash-bros-ultimate-1v1-sat-12-00-pm', '532139'): True,
    ('geekdom-3000', '1804189'): True,
    ('boulewar-4__ultimate-singles', '622109'): True,
    ('king-con__ssbu-1v1', '129129'): True,
    ('los-finos-monthly-10__los-finos-singles', '155461'): True,
    ('45-sp-1__1on1', '244649'): True,
    ('louisiana-comic-con-2024__super-smash-bros-ultimate-sat-12pm', '2264899'): True,
    ('spike-44__ultimate-singles', '622109'): True,
    ('3-itsukushima-3__singles', '876381'): False,
    ('circuito-paulista-de-i-smash-mar-o-2024__ultimate-singles', '1741316'): True,
    ('autopilot-club-22__ultimate-singles', '2250020'): True,
    ('couchwarriors-wa-march-2024-ranbat__ultimate-singles', '1044966'): True,
    ('kawaii-kon-2024__kawaii-kon-2024-main-event', '504242'): True,
    ('saturday-stadium-3-trials-and-tribulations__ultimate-singles', '39054'): True,
    ('el-rey-de-la-cueva__el-rey-de-la-cueva', '1036259'): True,
    ('neon-market__neon-fight-nights', '1788063'): True,
    ('neon-market__neon-fight-nights', '2778934'): True,
    ('neon-market__neon-fight-nights', '3592962'): False,
    ('el-dojo-masters-5-by-cintanegra-esports-1__ultimate-master-singles-pro', '173025'): True,
    ('ssbu-open-at-cecc-may-madness-2024__ultimate-singles', '158871'): False,
    ('ssbu-open-at-cecc-may-madness-2024__ultimate-singles', '44865'): False,
    ('get-on-my-level-x-canadian-fighting-game-championships__super-smash-bros-ultimate-singles', '2512815'): True,
    ('mongos-backyard-brawl__singles', '65489'): True,
    ('ultimate-challenger-series-4-grand-final__ultimate-singles', '180375'): True,
    ('smash-colosseum-3-2__smash-ultimate-1-v-1', '2252178'): True,
    ('ceo-2024-6__super-smash-bros-ultimate-1v1', '532139'): True,
    ('cherry-tree-2__ultimate-singles', '2986120'): True,
    ('luminosity-makes-big-moves-2024__ultimate-singles', '2286649'): False,
    ('luminosity-makes-big-moves-2024__ultimate-singles', '1042374'): False,
    ('patchwork-2024__ultimate-singles', '1042374'): False,
    ('max-rez__ultimate-singles-day-two', '1224902'): True,
    ('max-rez__ultimate-singles-day-two', '151544'): True,
    ('2024-convolution-chongqing-smash-tournament__1-1-1-on-1-battles', '2732977'): True,
    ('epitech-chase-18__singles', '323112'): True,
    ('nacional-julio-2024__singles', '2205508'): True,
    ('reaper-rumble-4-2__ultimate-singles', '1094952'): True,
    ('chill-out-2-drip-or-drown__ultimate-singles', '2986120'): True,
    ('supernova-2024__ultimate-1v1-singles', '300502'): True,
    ('lacome-dome-the-movie-by-st-albert-smash__ultimate-singles', '1035'): True,
    ('heavens-x-humber-summer-episode__super-smash-bros-ultimate-singles', '53613'): True,
    ('neon-market-2__neon-fight-nights', '1788063'): False,
    ('50-sp-3__1on1', '1160707'): True,
    ('beer-smash__singles', '128243'): True,
    ('smash-emblem-las-cuatro-casas__singles', '1433944'): True,
    ('bit-master-mty-22-secret-edition__super-smash-bros-ultimate-singles', '847880'): True,
    ('43-kurobra43__sp-1on1', '3211966'): True,
    ('3000-pot-bonus-cirque-du-cfl-4-ft-hurt-mkleo__smash-ultimate-1v1', '370802'): True,
    ('vgs-2024__ultimate-singles', '2076394'): False,
    ('vgs-2024__ultimate-singles', '30355'): True,
    ('encore-smash-monthy-39-250-pot-bonus__ultimate-singles-bracket', '1224902'): True,
    ('gobble-gobble-gauntlet-2024-ft-250-pot-bonus__ultimate-singles', '1259270'): False,
    ('posada-gamer-2024__smash-bros-ultimate-singles', '11154'): True,
    ('super-elite-monthly-series-xv-bigboss__ultimate-singles', '1895232'): True,
    ('trick-or-fortune__singles', '1175677'): True,
    ('posada-gamer-2024__smash-bros-ultimate-singles', '253333'): True,
    ('smash-awesome-1/singles', '2335377'): True,
    ('54-sp-2/1on1', '1498221'): True,
    ('the-comeback-finale-edition-100-pot-bonus/ultimate-singles', '1457345'): True,
    ('desert-knights-10/dk10-singles-lcq', '328340'): True,
    ('new-year-s-smash-dave-and-buster-s-300-pot/friday-night-fights-at-dave-and-buster-s', '241701'): True,
    ('the-versus-festival-habba-edition/super-smash-bros-ultimate', '3514626'): True,
    ('sela-homecoming/ultimate-singles-3-30pm', '1362071'): False,
    ('back-to-school-ranked-enero/singles', '71053'): True,
    ('y-to-jump/ultimate-singles', '21504'): True,
    ('j-popcon-fgc-tournament-2025/smash-bros-ultimate', '1474167'): True,
    ('luminosity-madness/smash-ultimate-singles', '21460'): True,
    ('ultimajac-jarabe-tapat-o/ultimate-singles', '1109290'): True,
    ('tds-x-sakura-smash-2/singles', '273243'): True,
    ('delfino-jam/smash-bros-ultimate', '741935'): True,
    ('the-game-expo-2025-fgc-fighting-games-tournament-1/smash-ultimate-the-game-expo', '220863'): False,
    ('el-rey-del-puerto-3ra-edici-n/ultimate-singles', '321295'): True,
    ('eba-talento/ultimate-singles', '2252178'): True,
    ('st-albert-arcade-37/ultimate-singles', '1006473'): False,
    ('elemental-rumble/ultimate-singles-experto', '131359'): True,
    ('valhalla-v/main-ultimate-singles', '1406048'): True,
    ('57-sp-1/1on1', '2461700'): True,
    ('episode-iv-ranked-mayo/singles', '71053'): True,
    ('the-hoosier-saga-finale/finale-invitational', '2143430'): True,
    ('pskshowdown-09-afterparty/singles', '1433944'): True,
    ('sweet-spot-9/ultimate-singles', '1087831'): False,
    ('la-sima-de-los-h-roes-2/singles', '137380'): True,
    ('smash-x-la-chibi-rocket-2025/ultimate-singles', '1310682'): False,
    ('comicpalooza-fight-club-2025-1/ultimate-singles-5-000-pot-bonus', '38776'): True,
    ('encore-smash-monthly-46-mr-e-s-last-dance/ultimate-singles-bracket', '1595628'): True,
    ('midtown-mayhem-6/singles-bracket', '1496295'): True,
    ('level-up-breakout-2025/ssbu-singles', '183480'): True,
    ('mas-all-del-muro/ultimate-singles-experto', '131359'): True,
    ('new-world-ranked-junio/singles', '2205508'): True,
    ('get-on-my-level-forever-canadian-fighting-game-championships/super-smash-bros-ultimate-singles', '44865'): True,
    ('mcdonald-s-smash-ultimate-6/smash-ultimate-singles', '261032'): True,
    ('60-sp-1/1on1', '2929281'): True,
    ('uas-las-finale/ultimate-apex-series-finale', '70916'): True,
    ('tryhaaards-20-long-live-the-king/singles-ultimate', '128243'): True,
    ('s-factor-12-1/smash-bros-ultimate-singles', '1250268'): True,
    ('s-factor-12-1/smash-bros-ultimate-singles', '1720743'): True,
    ('s-factor-12-1/smash-bros-ultimate-singles', '699618'): False,
    ('lost-level-smash-1/super-smash-bros-ultimate', '2375665'): True,
    ('rideae-farewell-tournament/ultimate-singles', '24971'): True,
    ('supernova-2025/ultimate-1v1-singles', '1063610'): True,
    ('supernova-2025/ultimate-1v1-singles', '12778'): True,
    ('san-japan-2025/sat-1pm-4pm-smash-ultimate-singles', '2538433'): True,
    ('the-big-bang-cgm-tournament/simple-smash', '3881688'): True,
    ('gone-fishin-2-back-from-the-depths/ultimate-singles', '234829'): True,
    ('eugenebound-summers/ultimate-singles', '12778'): True,
    ('fight-for-their-lives/ultimate-singles', '12099'): True,
    ('tomosmasher-4/ultimate-singles', '1250268'): True,
    ('play-sorbonne-festival-2025-ssbu/play-sorbonne-festival-ssbu-2025', '1179613'): False,
    ('play-sorbonne-festival-2025-ssbu/play-sorbonne-festival-ssbu-2025', '1406048'): False,
    ('z-z-s-fiv-rek-2025-bp-ssbu-local-9/ssbu-singles', '3724324'): True,
    ('sterling-clash-2025/smash-ultimate-singles', '873968'): True,
    ('mcdonald-s-smash-ultimate-8/smash-ultimate-singles', '330169'): True,
    ('4o4-by-sh33rz-smash-monthly-november/singles-4pm', '18802'): False,
    ('port-priority-9-10/ultimate-singles', '12778'): True,
    ('port-priority-9-10/ultimate-singles', '28679'): True,
    ('tec-in-place-4/ultimate-singles-1v1', '205133'): True,
    ('tec-in-place-4/ultimate-singles-1v1', '70916'): True,
    ('takers-summer-circuit-finale-lcq/circuit-finale', '1175674'): True,
    ('high-voltage-overload-2/ssbu-singles-1v1', '2065136'): True,
    ('high-voltage-overload-2/ssbu-singles-1v1', '207638'): True,
    ('ud-warriors/smash-ultimate-singles', '266003'): True,
    ('la-suite-7/ultimate-singles', '2062749'): True,
    ('expo-color/ultimate-singles', '2837550'): False,
    ('expo-color/ultimate-singles', '538881'): True,
    ('no-time-to-tilt-2025/smash-ultimate-singles-sa-so', '2981703'): True,
    ('icebreaker-ii/ultimate-singles-waterfall', '44865'): True,
    ('50-kurobra50/sp-1on1', '2320010'): True,
    ('4o4-by-sh33rz-final-smash-monthly/singles-4pm', '38830'): True,
    ('omg-2025-1/singles', '1386236'): True,
    ('el-bohio-de-bdaly-1/el-bohio-ultimate', '3006098'): True,
    ('stargate-classic-400-pot-bonus-holiday-party-ugly-sweater-contest/ultimate-singles', '15889'): True,
    ('talley-takeover-2026-winter-kickoff/ultimate-singles', '1820508'): True,
    ('citadel-2-1/ultimate-singles', '140568'): False,
    ('vars-ultimate-summit-1-the-return-of-smash-summit/swiss-playoffs', '370802'): True,
    ('vars-ultimate-summit-1-the-return-of-smash-summit/swiss-playoffs', '937555'): False,
    ('icebreaker-ii/ultimate-singles-waterfall', '539888'): True,
    ('fsc-retro-series-1-nes/super-smash-bros-ultimate-singles', '155461'): True,
    ('zamba-en-antikuna/zamba-en-antikuna', '701950'): True,
    ('let-s-make-big-moves-2026-7/ultimate-singles', '1216463'): False,
    ('let-s-make-big-moves-2026-7/ultimate-singles', '1250001'): False,
    ('let-s-make-big-moves-2026-7/ultimate-singles', '151544'): False,
    ('let-s-make-big-moves-2026-7/ultimate-singles', '1760115'): False,
    ('let-s-make-big-moves-2026-7/ultimate-singles', '2220603'): False,
    ('let-s-make-big-moves-2026-7/ultimate-singles', '231113'): False,
    ('let-s-make-big-moves-2026-7/ultimate-singles', '3097780'): False,
    ('zenkoku-taikai-4/zenkoku-taikai-4-ultimate-singles', '3101197'): True,
    ('ggcon-beyblade-x-super-smash-bros-ultimate-retro-turnuvalar/smash-ultimate', '2045761'): True,
    ('dr-insanos-bonfire-3/singles', '1250001'): True,
    ('campus-clash-3-barrage/ultimate-singles', '648817'): True,
    ('the-f-o-m-2-ahora-es-personal/ssbu-singles', '2525082'): True,
    ('brave-the-world-2/brave-the-world-1v1', '1352543'): False,
    ('chandelan-3-2026/1v1-ultimate-full-bo5', '1808977'): True,
    ('fodlan-winds-iii-x-lion-academy/ultimate-singles', '126381'): True,
    ('stock-of-love-ranked/singles', '71053'): True,
    ('reborn-3-1/singles', '131359'): True,
    ('midwest-battleground-2026/smash-ultimate-singles-1v1-open-bracket', '56436'): True,
    ('zenith-7-2/smash-ultimate-singles', '2344624'): False,
    ('sweet-spot-x/ultimate-singles', '151544'): True,
    ('dragon-s-realm-smash-regional-1000-prize-pool/smash-bros-ultimate-tournament-1v1-ct-regionals', '1784114'): True,
    ('to-win-7/singles', '1498221'): True,
    ('dead-zone-3-1/ssbu-singles-1v1', '1179613'): True,
    ('megacon-2026/ssbu-singles', '58217'): True,
    ('smash-pro-league-68/ultimate-singles', '3383425'): True,
    ('underline/smash-ultimate', '689500'): True,
    ('fuzzy-clash/ultimate-brackets', '3561053'): True,
    ('cecc-may-madness-2026/cecc-smash-ultimate-singles-open-bracket', '918277'): True,
    ('scarlet-classic-xi-500-pot-bonus/ultimate-singles', '267460'): True,
    ('15-kagaribi-15/singles', '1714828'): True,
    ('keep-the-momentum/main-event-1v1-smash-ultimate', '2959870'): True,
    ('tsunami-arena-zg/stunami-arena-zg', '4843677'): True,
    ('underline-2/smash-ultimate', '689500'): True,
    ('punch-punch-galaxy/ultimate-singles-experto', '131359'): False,
    ('hawaii-pacific-ultimate-24-3/hawaii-pacific-ultimate-24-ssbu-singles', '350926'): True,
    ('roll-for-grind-dragon-s-den-11/the-dragon-s-den', '53537'): True,
    ('couch-warriors-vic-june-2026-smash-ranking-battle/ultimate-singles', '2583707'): True,
    ('delta-open/main-sp-singles', '2858273'): True,
    ('147-2/road-to-top-monthly-tournament-s15e6', '1713595'): True,
    ('front-runners-41/ultimate-singles', '2150049'): True,
    ('patchwork-2026-a-love-letter/ultimate-singles', '1492978'): False,
    ('the-worst-18/singles-pro', '2252522'): True,
    ('the-worst-18/singles-pro', '273243'): True,
    ('fusion-300/ultimate-singles', '370802'): True,
    ('the-flamin-goat-x-smash-lez-x-mes-esport/flamin-goat-x', '173560'): True,
    ('the-flamin-goat-x-smash-lez-x-mes-esport/flamin-goat-x', '2959870'): True,
    ('kubox-cup-1/kubox-cup-smash', '373313'): False,
    ('origen-1/ultimate-singles', '1273444'): True,
    ('71-sp-1/1on1', '2757778'): True,
    ('ingobernable-1-nueva-sangre/ultimate-singles', '135042'): True,
    ('the-bigshow-monthly-2-camino-al-torneo-legendario/singles', '384927'): True,
    ('breach-2026-256-player-cap/ultimate-singles', '1872316'): True,
    ('s-factor-x3/smash-bros-ultimate-singles', '533613'): True,
    ('ultimate-apex-series-ii-natural-selection/ultimate-apex-series-finale', '1362071'): True,
    ('ultimate-singles-11-30am/ultimate-singles-11-00-am', '184005'): True,
    ('manoa-monthlies-101/manoa-monthlies-101-ssbu-singles', '144209'): True,
    ('versus-experience-tokon-edition/smash-ultimate', '1821059'): True,
    ('supernova-2026/ultimate-1v1-singles', '44865'): True,
    ('dat-blastzone-34/ultimate-singles', '1201971'): False,
    ('latte-esports-fighting-game-series-august/smash-ultimate-singles', '2491238'): True,
    ('nairbnb-esquenta-super-copa-2026/ultimate-singles', '390907'): False,
    ('mashito-go-6/smash-ultimate-singles', '1244573'): True,
    ('grand-wars-3-maesuma-grand-wars-3/singles-tournament', '2152604'): False,
    ('kill-kunfirm/ultimate-singles', '973738'): True,
    ('alpine-arena-summer-edition/ultimate-singles', '33730'): False,
    ('game-and-geek-expo-2026/super-smash-bros-ultimate-singles-main-bracket', '1820508'): True,
    ('lone-star-combat-2026/super-smash-bros-ultimate', '1245611'): True,
    ('smash-bros-ultimate-connecturday/torneo-singles-domingo', '326113'): True,
    ('sp13-umeburasp13/singles', '2226356'): True,
    ('sp13-umeburasp13/singles', '2486712'): True,
    ('sp13-umeburasp13/singles', '3519343'): False,
    ('kaycon-tribalero/smash-singles', '4843677'): True,
    ('smash-al-parche-13-edici-n-hidden/ultimate-singles', '973738'): True,
    ('jenzo-s-quantum-league-the-ascension/jql-the-ascension', '1336794'): True,
}

entrant_overrides = {
    'utasuma-himezuru-7': 39,
    'utasuma-himezuru-6': 48,
    'mamebura-12': 32,
    'dream-championship-series-2025/smash-ultimate-1v1-tournament': 173,
}

con = sqlite3.connect('ur_db_2026.db')
player_values, invitational_values = read_players()

player_values.append(PlayerValue('3C', '3292538', 40, '', ''))
player_values.append(PlayerValue('SSJ3', '3292537', 10, '', ''))
player_values.append(PlayerValue('Domino', '3301927', 30, '', '2024-01-01'))

tags = extract_tags(player_values)

# Range start, range end, expiration date
hb_ranges = [('2022-12-20', '2023-07-25', '2023-12-18'),
    ('2023-07-25', '2023-12-18', '2024-07-15'),
    ('2023-12-18', '2024-07-15', '2024-12-17'),
    ('2024-07-15', '2024-12-17', '2025-07-07'),
    ('2024-12-17', '2025-07-07', '2025-12-15'),
    ('2025-07-07', '2025-12-15', '2026-07-13'),
    ('2025-12-15', '2026-07-13', '2027-01-01'),
    ('2026-07-13', '2027-01-01', '2027-07-01')]

tiers = [(0, 500, 'D'), (500, 1000, 'C'), (1000, 2000, 'B'), (2000, 3000, 'B+'), (3000, 4000, 'A'), (4000, 5000, 'A+'), (5000, 6500, 'S'), (6500, 9000, 'S+'), (9000, 13000, 'P'), (13000, 17000, 'P+'), (17000, 999999, 'SP')]

hb_values = {
    'D': {},
    'C': {1: 30},
    'B': {1: 50, 2: 30, 3: 30, 4: 30},
    'B+': {1: 100, 2: 50, 3: 50, 4: 50, 5: 30, 7: 30},
    'A': {1: 150, 2: 100, 3: 100, 4: 100, 5: 50, 7: 50},
    'A+': {1: 150, 2: 100, 3: 100, 4: 100, 5: 50, 7: 50},
    'S': {1: 200, 2: 150, 3: 150, 4: 150, 5: 100, 7: 100, 9: 50, 13: 50},
    'S+': {1: 200, 2: 150, 3: 150, 4: 150, 5: 100, 7: 100, 9: 50, 13: 50},
    'P': {1: 250, 2: 200, 3: 200, 4: 200, 5: 150, 7: 150, 9: 100, 13: 100, 17: 50, 25: 50},
    'P+': {1: 250, 2: 200, 3: 200, 4: 200, 5: 150, 7: 150, 9: 100, 13: 100, 17: 50, 25: 50},
    'SP': {1: 300, 2: 250, 3: 250, 4: 250, 5: 200, 7: 200, 9: 150, 13: 150, 17: 100, 25: 100, 33: 50, 49: 50},
}

if __name__ == '__main__':
    # for p in player_values:
    #     print(str(p))
    # sys.exit()

    cur = con.cursor()

    cur.execute('SELECT id, value, date FROM tournaments')
    values = []

    for row in cur:
        values.append({'id': row[0], 'value': row[1], 'date': row[2], 'values': {}})

    recalculate = True

    iter_ = 0

    while recalculate:
        print('--------')
        new_values = []

        for tournament in values:
            tournament_value = calculate_value(tournament['id'])
            new_values.append(tournament_value)

        recalculate = False

        for i in range(len(values)):
            old_value = values[i]
            new_value = new_values[i]

            if old_value['id'] != new_value['id']:
                print('catastrophic failure')
                sys.exit()

            if old_value['value'] > new_value['value']:
                print('!!!!!')

            if get_tier(old_value['value']) != get_tier(new_value['value']):
                recalculate = True

                print('  tournament {} going from {} ({}) to {} ({})'.format(old_value['id'], get_tier(old_value['value']), old_value['value'], get_tier(new_value['value']), new_value['value']))

                new_tier = get_tier(new_value['value'])

                cur.execute('SELECT place, player_id FROM placings WHERE tournament_id = ?', (old_value['id'], ))

                new_player_values = []

                for row in cur:
                    if row[0] in hb_values[new_tier]:
                        new_player_values.append((row[0], row[1]))

                for new_player_value in new_player_values:
                    cur.execute('SELECT tag FROM players WHERE id = ?', (new_player_value[1], ))

                    tag = cur.fetchone()[0]
                    tags[new_player_value[1]] = tag
                    player_values.append(PlayerValue(tag, new_player_value[1], hb_values[new_tier][new_player_value[0]], get_hb_start_date(new_value['date']), get_hb_end_date(new_value['date'])))
                    print('  {} value -> {}'.format(tag, hb_values[new_tier][new_player_value[0]]))
            elif old_value['value'] != new_value['value']:
                print('    tournament {} going from {} to {}'.format(old_value['id'], old_value['value'], new_value['value']))

        values = new_values
        iter_ += 1

    with open('ultrank_tiering.csv', mode='w', newline='') as csvfile:
        csvwriter = csv.DictWriter(csvfile, fieldnames=['id', 'value', 'date', 'values'])

        csvwriter.writeheader()

        for value in values:
            csvwriter.writerow(value)

    confirm = input('check the file. type y to populate the database')
    if confirm.strip() == 'y':
        for value in values:
            cur.execute('UPDATE tournaments SET value = ? WHERE id = ?', (value['value'], value['id']))

        con.commit()

    