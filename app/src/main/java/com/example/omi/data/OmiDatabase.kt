```kotlin
@Database(entities = [Task::class], version = 2)
abstract class OmiDatabase : RoomDatabase() {
    abstract fun taskDao(): TaskDao

    companion object {
        @Volatile
        private var INSTANCE: OmiDatabase? = null

        fun getDatabase(context: Context): OmiDatabase {
            return INSTANCE ?: synchronized(this) {
                val instance = Room.databaseBuilder(
                    context.applicationContext,
                    OmiDatabase::class.java,
                    "omi_database"
                )
                    .addMigrations(MIGRATION_1_2)
                    .build()
                INSTANCE = instance
                instance
            }
        }

        private val MIGRATION_1_2 = object : Migration(1, 2) {
            override fun migrate(database: SupportSQLiteDatabase) {
                database.execSQL("ALTER TABLE tasks ADD COLUMN parentTaskId INTEGER DEFAULT NULL")
                database.execSQL("ALTER TABLE tasks ADD COLUMN indentationLevel INTEGER DEFAULT 0")
            }
        }
    }
}
