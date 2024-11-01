import controlflow as cf

# start by inspecting the volatility report for low IV rank stocks (for buy oppotunities) and monitoring the open positions for high IV rank stocks (for sell oppotunities)

# perform stock analysis for the selected stocks above

# check the general market sentiment (fear and greed index) for possible market inflection points

# also report a general trending stock -> this should be a section on the web app, consider also secondary effect


@cf.flow
def create_story():
    # get the topic from the user
    topic = cf.run(
        "Ask the user to provide a topic for a short story", interactive=True
    )

    # choose a genre
    genre_selector = cf.Agent(
        name="GenreSelector",
        instructions="You are an expert at selecting appropriate genres based on prompts.",
    )
    genre = genre_selector.run(
        "Select a genre for a short story",
        result_type=["Science Fiction", "Fantasy", "Mystery"],
        context=dict(topic=topic),
    )

    # choose a setting based on the genre
    if genre == "Science Fiction":
        setting = cf.run("Describe a distant planet in a binary star system")
    elif genre == "Fantasy":
        setting = cf.run("Create a magical floating city in the clouds")
    else:  # Mystery
        setting = cf.run("Design an isolated mansion with secret passages")

    # create a writer agent
    writer = cf.Agent(
        name="StoryWriter", instructions=f"You are an expert {genre} writer."
    )

    # create characters
    characters = writer.run(
        f"Create three unique characters suitable for a the provided genre, setting, and topic.",
        context=dict(genre=genre, setting=setting, topic=topic),
    )

    # write the story
    story = writer.run(
        f"Write a short story using the provided genre, setting, topic, and characters.",
        context=dict(genre=genre, setting=setting, topic=topic, characters=characters),
    )

    return dict(
        topic=topic,
        genre=genre,
        setting=setting,
        characters=characters,
        story=story,
    )


result = create_story()
print(result)
