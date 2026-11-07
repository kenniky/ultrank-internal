from startgg_toolkit import send_request
import json

def get_query(id_):
    query = '''query getId($id: ID!) {
  player(id: $id) {
    user {
      tournaments(query: {page: 1, perPage: 10}) {
        nodes {
          name
        }
      }
      authorizations(types: [TWITTER, TWITCH, DISCORD]) {
        type
        externalUsername
      }
      location {
        country
        state
        city
      }
      name
      slug
    }
    prefix
    gamerTag
  }
}'''
    variables = '''{{
        "id": {}
    }}'''.format(id_)

    return query, variables

if __name__ == '__main__':
    id_ = input('id: ')
    q, v = get_query(id_)
    r = send_request(q, v)
    print(json.dumps(r, indent=2, ensure_ascii=False))
