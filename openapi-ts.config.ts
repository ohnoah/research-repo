import { defineConfig } from '@hey-api/openapi-ts';

export default defineConfig({
    input: 'openapi.json',
    output: {
        path: 'src/client',
        format: 'prettier',
    },
    client: '@hey-api/client-fetch',
    // Additional type generation options
    types: {
        // Generate types with dates as Date objects instead of strings
        dates: 'types',
        // Enums generation strategy
        enums: 'javascript',
    },
});
