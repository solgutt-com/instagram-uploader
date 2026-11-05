# One-time setup (already done for @sol_gutt_foto)

This is the route that worked in November 2026. Meta changes its screens often.

## 1. Professional account
**@sol_gutt_foto** must be a **Creator** or **Business** account: Instagram app → Settings → Account type and tools.

## 2. Meta app
At developers.facebook.com there's an app called **SolGutt uploader**. Its use case is *Manage messaging & content on Instagram*, it's linked to a business portfolio, and it has a Unified-login configuration.

## 3. Token from a system user
At [business.facebook.com/settings](https://business.facebook.com/settings), inside the business portfolio:

1. **Accounts → Instagram accounts:** add `sol_gutt_foto`.
2. **Users → System users:** there's a system user named `uploader` (Admin).
3. **Assign assets:**
   - the app *SolGutt uploader*, with full control
   - `sol_gutt_foto`, with full control
4. **Generate token:**
   - App: *SolGutt uploader*
   - Expiration: **Never**
   - Permissions: `instagram_basic` and `instagram_content_publish`

   This gives a code starting with `EAA`. It never expires.

## 4. GitHub secrets
Add these at [repo → Settings → Secrets and variables → Actions](https://github.com/solgutt-com/instagram-uploader/settings/secrets/actions):

| Secret | Value |
|---|---|
| `IG_ACCESS_TOKEN` | the `EAA…` token |
| `IG_USER_ID` | @sol_gutt_foto's ID (Business Settings → Instagram accounts → sol_gutt_foto). Usually starts with 1784. |

Use the website form rather than the `gh secret set` command. With the command, it's easy to end up pasting the command itself instead of the token.

`config.json` has `"instagram_username": "sol_gutt_foto"`. If a token ever reaches a different account, the uploader refuses to post.

## 5. Test
GitHub → **Actions → Post to Instagram → Run workflow**, with **dry run** ticked.

The log should say `Token OK – connected to @sol_gutt_foto` and show the caption it would post.

## If the token is ever revoked
Generate a new one as in step 3, then update `IG_ACCESS_TOKEN`. The weekly *Refresh Instagram token* job does nothing for this kind of token, which is expected.
