# LinkLink - A Cross-game Item Link

This is a manual designed to emulate itemlinks across games.  It creates its own progression items and locations, and is designed to be as easy to use as possible.

## How to use

There are three key things to be aware of:

The first is item declarations.  Add new items to [items.json](data/items.json), adding games and their associated items to the `linklink` dictionary. Everything in a list will be made progressive, even if the original items weren't.

The second knob is a technical limitation.  The [Data Hooks](hooks/Data.py) contains a constant (`MAX_PLAYERS`) with the Maximum number of players that can be added to an itemlink.  There is no penalty for having extras other than some ID bloat, but we'd rather not have it too much higher than needed.

Note:  This is the maximum number of players in a link, not the total number of players in the multiworld.  If you have an 8 player multiworld, with Four players with Swords, and three players with Bicycles, you can safely have MAX_PLAYERS at 4.

Third, is a yaml setting `victims`.  You can leave this empty, and it will plando every valid player in the multiworld.  But if you only want to affect a subset of players, put their names in here.

Note: linklink will attempt to respect some of the players options
like plando (if plando item enabled), local items and/or itemlinks
EG. if a player mark their sword to be local then all of their swords will be excluded from linklink  
Another thing to note is that unlike normal itemlinks, which are conservative with the pool, linklink is greedy.  If one player has 3 swords and another player has five, LinkLink will take as many as possible from each player.  You DO NOT need to worry about yaml settings affecting the numbers of items in the pool.

You DO NOT need to hand-define plando, or even have plando enabled in host.yaml.  The LinkLink world will force placement of the items it wants to steal automatically.

## Item Definitions

This is an extension of the standard Manual item definition.

```json
    {
        "name": "Shield", // Name of the item as it appears in the client and other players.
        "count": 6,  // Maximum in pool.  Any above this number won't be plando'd
        "extra": 1, // Optional counts of extra copies of keys that will not create new levels of locations
        "linklink": {  // This is the important part:
            "Links Awakening DX": ["Progressive Shield"],  
            // Progressive items are pulled multiple times.  We'll pull all three Progressive Shields.
            "Tunic": ["Shield"],
            // Tunic only has one shield.  Nothing will happen when the link recieves shields 2 and 3.
            "A Link to the Past": ["Blue Shield", "Red Shield", "Mirror Shield"], 
            // LttP has three separate shields.  This will progressify them.
            "Ocarina of Time": ["Progressive Shield", "Deku Shield", "Hylian Shield", "Mirror Shield"], 
            // If a game has the option to be progressive or not, this uses progressives if it can find any, then the individuals afterwards.
            "Factorio": ["progressive-armor", "progressive-energy-shield"],  
            // You can even progressify progressives!  This'll give all four Armor upgrades, then the two Energy Shield modules.
            "Shuffle Example": ["Shield A", "Shield B", "Shield C", "$Shuffle"], 
            // Something you can do in this fork of linklink is to add the special "$Shuffle" fake item that will make linklink randomly choose the order of items placed for this game
            "ItemGroup Example": ["Shields"], 
            // With this fork you can use an item group instead of listing all the items, every items in that item group will be possibly used
            "Buffer Example": ["Shield A", "$Buffer_2", "Shield B"],
            // Also with this fork, you can insert filler items in between other items, so that player with this will receive the following:
            // "Shield A" -> "Filler from their game" -> "Filler from their game" -> "Shield B"
            // you can put whatever number you want after the `_` not just 2
            // one thing to note is that the code will cap the maximum of buffer created so that the total number of possible items to use will never exceed the "count" property
            // if instead of "$Buffer_2" it was "$Buffer_20" since the "count" is set to 6 there would actually be only 4 filler created (assuming both shield only have 1 copy each in the pool)
            "The Legend of Zelda": ["Magical Shield"],
            "SMZ3": ["ProgressiveShield"],
            "Wind Waker": ["Progressive Shield"],
        }
    }
```

## How does this work?

Locations are automatically created by [after_load_location_file](hooks/Data.py), and item placement and culling is done in [after_generate_basic](hooks/World.py).  

Distribution can done by hand using the Manual Client, but it is recommended that you use the [Slow Release Client](https://github.com/gjgfuj/AP-SlowRelease/releases) to automatically send items out as they come into Logic.
