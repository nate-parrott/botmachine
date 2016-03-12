import commanding

def examples():
    example_phrases = []
    # add baseline nonsense parses:
    example_phrases.append(commanding.Phrase("", ["ihrfeiiehrgogiheog"]))
    example_phrases.append(commanding.Phrase("", ["ihrfeio iehrgogih eog"]))
    example_phrases.append(commanding.Phrase("", ["eyfght oehrgueig erobf", ["ehheiog","hegoegn"]]))
    example_phrases.append(commanding.Phrase("", ["wurt turt gurt", ["~burt", "nurt"]]))
    example_phrases.append(commanding.Phrase("", [["~uirguieg", "hgeough egoiheroi"]]))
    example_phrases.append(commanding.Phrase("", [["~uirguieg", "hgeough egoiheroi"]]))
    example_phrases.append(commanding.Phrase("", ["what", ["~uirguieg", "hgeough egoiheroi"]]))
    example_phrases.append(commanding.Phrase("", [["~uirguieg", "hgeough egoiheroi ehgiegeg"]]))
    example_phrases.append(commanding.Phrase("", [["~uirguieg", "hgeough egoiheroi ehgiegeg riehg hierohgi"]]))
    example_phrases.append(commanding.Phrase("", [["~uirguieg", "hgeoughegoiheroi"]]))
    return example_phrases
