# upbank

Work in progress -- a high level interface to the Up bank API.

Example:

    import upbank
    token =  'up:...' # put your own token here
    up = upbank.Up(token)
    trns = up.gettransactions(2024,cache=True)
    up.summarise(trns)
