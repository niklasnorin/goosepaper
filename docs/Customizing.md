# Customizing Your Feed

Goosepaper now uses a strict v2 config model:

- One paper config file for the paper itself.
- One optional user config file for delivery defaults.
- CLI flags decide whether delivery happens at all.

## Paper Config

Paper configs are JSON files with `"version": 2`.
If you do not pass `--config`, Goosepaper looks for `./goosepaper.json`.

Example:

```json
{
    "version": 2,
    "paper": {
        "title": "Jordan's Daily Goosepaper",
        "subtitle": "",
        "style": "FifthAvenue",
        "font_size": 14,
        "table_of_contents": true,
        "layout": "auto",
        "page_profile": "remarkable2"
    },
    "sources": [
        {
            "type": "weather",
            "lat": 59.3293,
            "lon": 18.0686,
            "unit": "F"
        },
        {
            "type": "wikipedia"
        },
        {
            "type": "rss",
            "url": "https://feeds.npr.org/1001/rss.xml",
            "limit": 5,
            "byline": "first",
            "body_source": "auto"
        },
        {
            "type": "reddit",
            "subreddit": "news"
        }
    ],
    "delivery": {
        "folder": "Morning Brief"
    }
}
```

## User Config

User-level delivery defaults live in `~/.config/goosepaper/config.json`.
These defaults are optional and only affect delivery.

Example:

```json
{
    "version": 2,
    "delivery_defaults": {
        "folder": "News",
        "replace_mode": "nocase",
        "cleanup": false
    }
}
```

Supported `delivery_defaults` fields:

| Field | Type | Default | Description |
| ----- | ---- | ------- | ----------- |
| `folder` | str or null | `null` | Default destination folder on your reMarkable. |
| `replace_mode` | str | `"never"` | Collision behavior. One of `"never"`, `"exact"`, or `"nocase"`. |
| `cleanup` | bool | `false` | Delete the output file after a successful delivery. |

The paper config's `delivery` section only supports `folder`.
Delivery still happens only when you run Goosepaper with `--deliver`.

## Printing

Goosepaper can also send the finished paper straight to a network printer that
speaks IPP (which is what AirPrint uses). Most home printers do, including the
Canon TS5350a. No CUPS or printer driver is required: Goosepaper talks to the
printer directly over the local network, which works well from a container on a
home server as long as the container can reach the printer's IP.

Add a `printing` section to your paper config:

```json
{
    "version": 2,
    "paper": {},
    "sources": [],
    "printing": {
        "printer": "192.168.1.42",
        "copies": 1,
        "media": "iso_a4_210x297mm",
        "sides": "two-sided-long-edge",
        "color_mode": "monochrome"
    }
}
```

| Field | Type | Default | Description |
| ----- | ---- | ------- | ----------- |
| `printer` | str or null | `null` | Printer address. A hostname (`TS5350a.local`), an IP (`192.168.1.42`), or a full `ipp://`/`ipps://` URI. Bare addresses become `ipp://<address>:631/ipp/print`. |
| `copies` | int | `1` | How many copies to print. |
| `media` | str or null | `null` | Paper size keyword, such as `iso_a4_210x297mm` or `na_letter_8.5x11in`. When omitted, the printer's own default is used. |
| `sides` | str | `"one-sided"` | One of `"one-sided"`, `"two-sided-long-edge"`, or `"two-sided-short-edge"`. |
| `color_mode` | str | `"monochrome"` | One of `"auto"`, `"color"`, or `"monochrome"`. |

The same fields can go in the user config as `print_defaults`, and the paper
config wins where both set a value.

Printing only happens when you pass `--print`:

```shell
uv run goosepaper --print
```

Because papers are laid out for e-ink by default, set
`"page_profile": "a4"` (or `"letter"`) in the `paper` section when the paper is
destined for a physical printer.

To print every morning, run Goosepaper on a schedule (cron on the host, or a
scheduled container run in Portainer):

```shell
0 6 * * * docker run --rm -v /srv/goosepaper:/goosepaper/mount j6k4m8/goosepaper \
    goosepaper -c mount/goosepaper.json -o mount/Goosepaper.pdf --print
```

The container needs network access to the printer, so run it on a network that
can reach the printer's IP (Docker's default bridge network usually can, since
it routes through the host).

## CLI Overrides

These flags apply to a single run:

```shell
uv run goosepaper --deliver --folder Inbox --replace-mode exact --cleanup
```

Available delivery flags:

- `--deliver`
- `--folder`
- `--replace-mode`
- `--cleanup`
- `--no-cleanup`

Available printing flags:

- `--print`
- `--printer`
- `--copies`
- `--media`
- `--sides`
- `--color-mode`

`--deliver` and `--print` are independent, so a single run can do both.

Run-specific options like `--output` and `--nostory` are CLI-only and do not belong in config files.

## Paper Settings

The `paper` object supports:

| Field | Type | Default | Description |
| ----- | ---- | ------- | ----------- |
| `title` | str or null | `null` | The paper title. If omitted, Goosepaper uses its built-in default title. |
| `subtitle` | str or null | `null` | Optional subtitle shown under the title. |
| `style` | str | `"FifthAvenue"` | One of the built-in themes. Themes control typography, rules, spacing, and the general voice of the page. |
| `font_size` | int | `14` | Base reading size for the page. Headings, ears, and utility text scale from this value. |
| `body_font` | str or null | `null` | Optional override for the body font family while keeping the rest of the theme intact. |
| `table_of_contents` | bool | `false` | Optional linked contents block near the top of the issue. In PDF output the links are internal document links. |
| `layout` | str | `"auto"` | Layout override. One of `"auto"`, `"1col"`, `"2col"`, or `"3col"`. |
| `page_profile` | str | `"remarkable2"` | Target page shape. One of `remarkable1`, `remarkable2`, `paper_pro`, `paper_pro_move`, `letter`, or `a4`. (`rm1` also works.) |

Built-in themes:

- `Academy`
- `FifthAvenue`
- `Autumn`
- `GrayMaiden`

With `"layout": "auto"`, Goosepaper chooses a sensible default from the page profile:

- `remarkable1`, `remarkable2`, and `paper_pro_move` default to a single reading column
- `paper_pro`, `letter`, and `a4` default to denser multi-column layouts
- Explicit `"1col"`, `"2col"`, and `"3col"` still override that default

Ears only render when the story mix actually includes `EAR` content, such as weather. The table of contents is independent and only appears when `paper.table_of_contents` is `true`.

`page_profile` is independent of `style` and `layout`. It controls the target page geometry and density envelope so Goosepaper can produce surfaces tuned for:

- `remarkable1`
- `remarkable2`
- `paper_pro`
- `paper_pro_move`
- `letter`
- `a4`

## Sources

The `sources` array describes which providers to include.
Each source entry has a `"type"` plus provider-specific fields.

### Text

```json
{
    "type": "text",
    "headline": "This is a headline",
    "text": "This is some text"
}
```

| Field | Type | Default | Description |
| ----- | ---- | ------- | ----------- |
| `headline` | str | `null` | Headline to use. |
| `text` | str | `null` | Body text to use. |
| `limit` | int | `5` | Number of paragraphs to generate when `text` is omitted. |

### Reddit

```json
{
    "type": "reddit",
    "subreddit": "news"
}
```

| Field | Type | Default | Description |
| ----- | ---- | ------- | ----------- |
| `subreddit` | str | none | The subreddit to use. |
| `limit` | int | `20` | Number of stories to fetch. |
| `since_days_ago` | number | `null` | If provided, filter stories by recency. |

### RSS

```json
{
    "type": "rss",
    "url": "https://feeds.npr.org/1001/rss.xml",
    "limit": 5,
    "byline": "first",
    "body_source": "auto"
}
```

| Field | Type | Default | Description |
| ----- | ---- | ------- | ----------- |
| `url` | str | none | RSS feed URL. |
| `limit` | int | `5` | Number of stories to fetch. |
| `since_days_ago` | number | `null` | If provided, filter stories by recency. |
| `byline` | str | `"all"` | One of `"all"`, `"none"`, or `"first"` for RSS source attribution. |
| `body_source` | str | `"auto"` | One of `"auto"`, `"content"`, `"summary"`, or `"article"` to choose where RSS story bodies come from. |

RSS `body_source` modes:

- `auto`: prefer embedded feed content; otherwise fetch the linked article and fall back to feed-provided body text
- `content`: prefer embedded feed content and fall back to summary/description without fetching the article page
- `summary`: prefer summary/description and fall back to embedded feed content without fetching the article page
- `article`: force linked-article extraction first and only fall back to feed-provided body text if needed

### Mastodon

```json
{
    "type": "mastodon",
    "server": "https://neuromatch.social",
    "username": "jordan",
    "limit": 8
}
```

| Field | Type | Default | Description |
| ----- | ---- | ------- | ----------- |
| `server` | str | none | Mastodon server URL. |
| `username` | str | none | Mastodon username to use. |
| `limit` | int | `5` | Number of entries to fetch. |
| `since_days_ago` | number | `null` | If provided, filter stories by recency. |

### Bluesky

```json
{
    "type": "bluesky",
    "username": "jordan.matelsky.com",
    "limit": 8,
    "include_replies": false
}
```

| Field | Type | Default | Description |
| ----- | ---- | ------- | ----------- |
| `username` | str | none | Bluesky handle to fetch, with or without a leading `@`. |
| `limit` | int | `5` | Number of posts to fetch. |
| `since_days_ago` | number | `null` | If provided, filter posts by recency. |
| `include_replies` | bool | `true` | Whether to include replies in the fetched author feed. |

Bluesky sources use Bluesky's unauthenticated public AppView endpoints.

### Readwise Reader

```json
{
    "type": "readwise",
    "token_env": "READWISE_TOKEN",
    "location": "later",
    "category": "article",
    "tags": ["morning"],
    "limit": 5,
    "body_source": "text"
}
```

| Field | Type | Default | Description |
| ----- | ---- | ------- | ----------- |
| `token_env` | str | `"READWISE_TOKEN"` | Environment variable containing the Readwise access token. |
| `limit` | int | `5` | Number of Reader documents to fetch. |
| `since_days_ago` | number | `null` | If provided, fetch Reader documents updated recently. |
| `location` | str or null | `"later"` | One of `"new"`, `"later"`, `"shortlist"`, `"archive"`, or `"feed"`. Set `null` to omit this filter. |
| `category` | str or null | `"article"` | One of `"article"`, `"email"`, `"rss"`, `"highlight"`, `"note"`, `"pdf"`, `"epub"`, `"tweet"`, or `"video"`. Set `null` to omit this filter. |
| `tags` | list[str] | `[]` | Reader tags to require. Readwise matches documents that have all listed tags. |
| `body_source` | str | `"text"` | One of `"text"`, `"html"`, or `"summary"`. |

Readwise `body_source` modes:

- `text`: fetch Reader HTML content, extract readable text blocks with BeautifulSoup, and let Goosepaper handle the page layout
- `html`: fetch Reader HTML content and pass cleaned HTML through to Goosepaper
- `summary`: render only the Reader summary and do not request full HTML content

Set the token before running Goosepaper:

```shell
export READWISE_TOKEN="..."
```

### Weather

```json
{
    "type": "weather",
    "lat": 42.3601,
    "lon": -71.0589,
    "unit": "F",
    "mode": "hourly",
    "hours": 12,
    "step_hours": 4,
    "clock_format": "12h"
}
```

| Field | Type | Default | Description |
| ----- | ---- | ------- | ----------- |
| `lat` | number | none | Latitude of the forecast location. |
| `lon` | number | none | Longitude of the forecast location. |
| `unit` | str | `"F"` | Temperature unit. Either `"F"` or `"C"`. |
| `timezone` | str | `"America/New_York"` | Timezone for the forecast request. |
| `mode` | str | `"summary"` | One of `"summary"`, `"hourly"`, `"daily"`, or `"hourly_daily"`. |
| `hours` | int | `12` | For hourly mode, how many hours ahead to include. |
| `step_hours` | int | `4` | For hourly mode, how many hours to skip between forecast points. |
| `days` | int | `4` | For daily mode, how many days to include. |
| `clock_format` | str | `"12h"` | For hourly labels, either `"12h"` or `"24h"`. |

Weather rendering modes:

- `summary`: compact current behavior, rendered in the paper ear.
- `hourly`: a breakdown like `12pm`, `4pm`, `8pm`, rendered as a full-width utility strip when the request is richer than a compact summary.
- `daily`: a multi-day high/low forecast, also promoted to the utility strip when it would be too large for the ear.
- `hourly_daily`: a combined utility-strip module with both the hourly and daily forecast sections.

### Wikipedia

```json
{
    "type": "wikipedia"
}
```

This source returns the current events section from Wikipedia.
It does not accept any additional fields.
